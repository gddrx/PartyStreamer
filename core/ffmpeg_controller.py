import json
import subprocess
import threading
from typing import Callable

from core.ffmpeg_path import get_ffmpeg_path, get_ffprobe_path, get_logger
from core.quality_presets import PRESETS, DEFAULT_PRESET
from core.stats_parser import parse_line, format_size_kb


class StreamController:
    """Manage an ffmpeg streaming subprocess with HW acceleration and auto-reconnect."""

    def __init__(self, on_stats: Callable[[dict], None], on_error: Callable[[str], None], on_started: Callable[[], None]):
        self._logger = get_logger("StreamController")
        self._process: subprocess.Popen | None = None
        self._read_thread: threading.Thread | None = None
        self._stdout_thread: threading.Thread | None = None
        self._on_stats = on_stats
        self._on_error = on_error
        self._on_started = on_started

        # Auto-reconnect state
        self._is_active = False
        self._first_stats_received = False
        self._reconnect_timer: threading.Timer | None = None
        self._last_params: dict = {}
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 2
        self._stop_event = threading.Event()

        # Detected hardware encoder
        self._hw_encoder = self._detect_hw_encoder()

    def _build_osd_filter(self, video_duration: float, seek_pos: float = 0) -> str:
        """Build a drawtext OSD filter that works with ffmpeg 8.x and accounts for seek position."""
        # Use seek_pos as gmtime offset to show correct absolute video time
        return (
            f"drawtext=text=' %{{pts\\:gmtime\\:{int(seek_pos)}\\:%H\\\\\\:%M\\\\\\:%S}} ':"
            "x=w-tw:"
            "y=h-th:"
            "fontcolor=gray:"
            "fontsize=h/30:"
            "bordercolor=black:"
            "borderw=2:"
            "box=1:"
            "boxcolor=black@0.6:"
            "boxborderw=4"
        )

    def _detect_hw_encoder(self) -> str:
        """Check for available hardware encoders (NVENC or VAAPI)."""
        ffmpeg = get_ffmpeg_path()
        if not ffmpeg:
            return "libx264"
        
        try:
            res = subprocess.run([ffmpeg, "-encoders"], capture_output=True, text=True, timeout=5)
            if "h264_nvenc" in res.stdout:
                self._logger.info("Hardware acceleration: NVIDIA NVENC detected")
                return "h264_nvenc"
            if "h264_vaapi" in res.stdout:
                self._logger.info("Hardware acceleration: VAAPI detected")
                return "h264_vaapi"
        except Exception:
            self._logger.warning("Failed to detect hardware encoders, falling back to libx264")
        
        return "libx264"

    @property
    def is_streaming(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self, url: str, video_path: str, quality: str, seek_pos: float = 0, audio_index: int = 0, osd_enabled: bool = False, video_duration: float = 0, use_software_fallback: bool = False):
        """Start ffmpeg streaming. Stops any previous stream first."""
        self._logger.debug("[start] stopping old stream")
        self.stop(cancel_reconnect=False)
        self._logger.debug("[start] clearing stop_event, setting is_active=True")
        self._stop_event.clear()
        self._is_active = True
        self._first_stats_received = False
        self._last_params = {
            "url": url, "video_path": video_path, "quality": quality,
            "seek_pos": seek_pos, "audio_index": audio_index,
            "osd_enabled": osd_enabled, "video_duration": video_duration,
        }
        
        self._logger.info("Starting stream: quality=%s, seek=%.1fs, audio_index=%d, encoder=%s, osd=%s",
                           quality, seek_pos, audio_index, self._hw_encoder, osd_enabled)

        cmd = self._build_command(url, video_path, quality, seek_pos, audio_index, osd_enabled, video_duration)
        if not cmd:
            self._on_error("ffmpeg not found.")
            return

        self._logger.debug("ffmpeg command: %s", " ".join(cmd))
        try:
            self._process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                bufsize=0, universal_newlines=False,
            )
            self._read_thread = threading.Thread(target=self._read_stderr, daemon=True)
            self._read_thread.start()
            self._stdout_thread = threading.Thread(target=self._read_stdout, daemon=True)
            self._stdout_thread.start()
            
            # Watcher thread for unexpected exit
            threading.Thread(target=self._wait_for_exit, daemon=True).start()
            
        except Exception as e:
            self._logger.exception("Failed to start ffmpeg")
            self._on_error(f"Failed to start ffmpeg: {e}")

    def _build_command(self, url: str, video_path: str, quality: str, seek_pos: float = 0, audio_index: int = 0, osd_enabled: bool = False, video_duration: float = 0) -> list[str] | None:
        """Construct the FFmpeg command list."""
        ffmpeg = get_ffmpeg_path()
        if not ffmpeg:
            return None

        preset = PRESETS.get(quality, PRESETS[DEFAULT_PRESET])
        vb = preset["vb"]
        ab = preset["ab"]

        if vb == "auto" or ab == "auto":
            probed = self._probe_bitrates(video_path)
            if vb == "auto": vb = probed.get("vb")
            if ab == "auto": ab = probed.get("ab")

        cmd = [ffmpeg, "-y", "-re", "-stats_period", "1"]

        # Input-side seek — must be BEFORE -i, especially with -re
        if seek_pos > 0:
            cmd += ["-ss", f"{seek_pos:.2f}"]

        cmd += ["-i", video_path]

        # Stream mapping
        cmd += ["-map", "0:v:0", "-map", f"0:a:{audio_index}"]

        # Video encoding with HW acceleration
        if vb:
            cmd += ["-c:v", self._hw_encoder]
            if self._hw_encoder == "libx264":
                cmd += ["-preset", preset["preset"], "-b:v", vb]
            elif self._hw_encoder == "h264_nvenc":
                cmd += ["-preset", "p4", "-b:v", vb]
            elif self._hw_encoder == "h264_vaapi":
                cmd += ["-b:v", vb]
        
        vf_filters = []
        if preset.get("scale"):
            vf_filters.append(preset["scale"])

        if osd_enabled and video_duration > 0:
            osd_filter = self._build_osd_filter(video_duration, seek_pos)
            vf_filters.append(osd_filter)

        if vf_filters:
            cmd += ["-vf", ",".join(vf_filters)]
        
        if ab:
            cmd += ["-c:a", "aac", "-b:a", ab, "-ar", "44100"]

        cmd += ["-f", "flv", url]
        return cmd

    def _wait_for_exit(self, use_software_fallback: bool = False):
        """Monitor ffmpeg process and trigger auto-reconnect if it crashes."""
        process = self._process
        if not process:
            self._logger.debug("[_wait_for_exit] process is None, exiting")
            return
        
        self._logger.debug("[_wait_for_exit] waiting for ffmpeg pid=%d", process.pid)
        retcode = process.wait()

        # RACE CONDITION FIX: If self._process is no longer this process, 
        # it means stop() or a new start() has already moved on.
        if self._process is not process:
            self._logger.debug("[_wait_for_exit] process %d is no longer current, ignoring exit", process.pid)
            return

        # Check for failure to initialize HW encoder
        if retcode != 0 and not self._stop_event.is_set():
            if not use_software_fallback and self._hw_encoder != "libx264" and retcode in [1, 255]:
                self._logger.warning("HW encoder failed (code %d). Retrying with software encoding.", retcode)
                self._on_error("HW encoder failed, switching to software...")
                self.start(**self._last_params, use_software_fallback=True)
                return
            
            # If we are already using software fallback or got a different fatal error
            self._logger.error("FFmpeg exited with fatal code %d.", retcode)
            self._on_error(f"FFmpeg crashed (code {retcode}). Check URL/Log.")
            self._is_active = False
            return

        # Read any remaining stderr that the reader thread missed
        remaining = b""
        try:
            remaining = process.stderr.read()
            process.stderr.close()
        except Exception:
            pass

        remaining_text = remaining.decode(errors="replace").strip() if remaining else ""
        if remaining_text:
            for line in remaining_text.splitlines():
                self._logger.debug("ffmpeg stderr: %s", line.strip())

        self._logger.debug("[_wait_for_exit] ffmpeg pid=%d exited with code %d, stop_event=%s, is_active=%s",
                          process.pid, retcode, self._stop_event.is_set(), self._is_active)
        
        # Only reconnect if not a controlled stop
        if self._stop_event.is_set():
            self._logger.debug("[_wait_for_exit] controlled stop, ignoring exit")
            return
        
        if self._is_active and retcode != 0:
            self._logger.warning("ffmpeg exited unexpectedly (code %d). Reconnecting in 3s...", retcode)
            if self._reconnect_timer:
                self._reconnect_timer.cancel()
            
            self._reconnect_timer = threading.Timer(3.0, self._handle_reconnect)
            self._reconnect_timer.start()
        elif not self._is_active:
            self._logger.debug("[_wait_for_exit] not active, ignoring exit (code=%d)", retcode)
        elif retcode == 0:
            self._logger.debug("[_wait_for_exit] clean exit (code=0), no reconnect needed")

    def _handle_reconnect(self):
        if not self._is_active:
            return
        
        self._reconnect_attempts += 1
        if self._reconnect_attempts > self._max_reconnect_attempts:
            self._logger.error("Max reconnect attempts reached. Giving up.")
            self._is_active = False
            self._on_error("Stream failed after multiple reconnect attempts.")
            return
        
        self._logger.info("Attempting auto-reconnect (%d/%d)...", self._reconnect_attempts, self._max_reconnect_attempts)
        self.start(**self._last_params)

    def get_audio_tracks(self, video_path: str) -> list[dict]:
        """Probe file for audio streams. Returns list of {index, title}."""
        tracks = []
        try:
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v", "quiet",
                    "-print_format", "json",
                    "-show_streams",
                    video_path,
                ],
                capture_output=True, text=True, timeout=15,
            )
            info = json.loads(probe.stdout)
            audio_count = 0
            for stream in info.get("streams", []):
                if stream.get("codec_type") == "audio":
                    tags = stream.get("tags", {})
                    title = tags.get("title")
                    if not title or "handler" in title.lower():
                        title = f"Audio Track {audio_count:02d}"
                    
                    tracks.append({
                        "index": audio_count,
                        "description": title,
                        "codec": stream.get("codec_name", "unknown")
                    })
                    audio_count += 1
        except Exception:
            self._logger.exception("Failed to probe audio tracks for %s", video_path)
        return tracks

    def _read_stderr(self):
        buf = ""
        while True:
            # Check if process is still active and stderr exists
            if not self._process or not self._process.stderr:
                break
            try:
                chunk = self._process.stderr.read(4096)
                if not chunk:
                    break
                text = chunk if isinstance(chunk, str) else chunk.decode(errors="replace")
                
                # Add to buffer and split by both \r and \n to catch stats and logs
                buf += text
                # Normalize line endings for splitting
                temp_buf = buf.replace("\r\n", "\n").replace("\r", "\n")
                parts = temp_buf.split("\n")
                
                # If the last character wasn't a newline, the last part is incomplete
                if not (text.endswith("\n") or text.endswith("\r")):
                    buf = parts.pop()
                else:
                    buf = ""

                for line in parts:
                    line = line.strip()
                    if not line:
                        continue

                    # Trigger 'started' as soon as we see encoding info or first stats
                    if not self._first_stats_received:
                        if "Press [q] to stop" in line or "frame=" in line or "bitrate=" in line:
                            self._logger.info("Stream activity detected: %s. Triggering on_started.", line[:30])
                            self._first_stats_received = True
                            self._on_started()

                    stats = parse_line(line)
                    if stats:
                        self._on_stats(stats)
                    else:
                        if "frame=" in line or "bitrate=" in line:
                            self._logger.debug("Stats regex failed to match line: %s", line)
                        else:
                            self._logger.debug("ffmpeg: %s", line)
            except Exception:
                # Process might have been closed during read
                break

    def _read_stdout(self):
        if not self._process or not self._process.stdout:
            return
        try:
            for line in iter(self._process.stdout.readline, b""):
                pass
        except Exception:
            pass

    def _probe_bitrates(self, video_path: str) -> dict:
        """Return dict with vb and/or ab strings (e.g. '8000k') from source file."""
        result = {}
        ffprobe = get_ffprobe_path()
        if not ffprobe:
            self._logger.error("ffprobe not found, cannot probe bitrates")
            return result
            
        try:
            probe = subprocess.run(
                [
                    ffprobe,
                    "-v", "quiet",
                    "-print_format", "json",
                    "-show_streams",
                    "-show_format",
                    video_path,
                ],
                capture_output=True, text=True, timeout=15,
            )
            info = json.loads(probe.stdout)
            for stream in info.get("streams", []):
                if stream.get("codec_type") == "video" and not result.get("vb"):
                    bits = int(stream.get("bit_rate", 0) or 0)
                    if bits: result["vb"] = f"{bits // 1000}k"
                elif stream.get("codec_type") == "audio" and not result.get("ab"):
                    bits = int(stream.get("bit_rate", 0) or 0)
                    if bits: result["ab"] = f"{bits // 1000}k"
            
            fmt_bits = info.get("format", {}).get("bit_rate")
            if fmt_bits and not result.get("vb") and not result.get("ab"):
                result["vb"] = f"{int(fmt_bits) // 1000}k"
        except Exception:
            self._logger.exception("Failed to probe bitrates")
        return result

    def seek(self, url: str, video_path: str, quality: str, position: float, audio_index: int = 0, osd_enabled: bool = False, video_duration: float = 0):
        """Restart stream at the given position in seconds."""
        self._logger.info("[seek] restarting stream at %.1fs", position)
        self._reconnect_attempts = 0
        self.start(url, video_path, quality, seek_pos=position, audio_index=audio_index, osd_enabled=osd_enabled, video_duration=video_duration)

    def stop(self, cancel_reconnect: bool = True):
        self._logger.debug("[stop] cancel_reconnect=%s, process=%s", cancel_reconnect, self._process.pid if self._process else None)
        self._stop_event.set()
        if cancel_reconnect:
            self._is_active = False
            if self._reconnect_timer:
                self._reconnect_timer.cancel()

        if self._process and self._process.poll() is None:
            self._logger.debug("[stop] terminating ffmpeg pid=%d", self._process.pid)
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._logger.debug("[stop] kill timeout, forcing pid=%d", self._process.pid)
                self._process.kill()
        else:
            self._logger.debug("[stop] no process to terminate")

        self._process = None
        self._read_thread = None
        self._stdout_thread = None
        self._logger.debug("[stop] done")
