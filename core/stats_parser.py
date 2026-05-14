import logging
import re

_logger = logging.getLogger("PartyPlayer.stats_parser")

_stats_re = re.compile(
    r"frame=\s*(\d+)\s+"
    r"(?:fps=\s*([\d.]+)\s+)?"
    r"(?:q=\s*[\d.-]+\s+)?"
    r"(?:L)?size=\s*(\d+)(KiB|kB|MiB|MB)\s+"
    r"time=(\d+:\d+:\d+\.?\d*)\s+"
    r"bitrate=\s*([\d.]+)k?bits/s\s+"
    r"speed=\s*([\d.]+)x"
)


def parse_line(line: str) -> dict | None:
    """Parse a single ffmpeg stderr line into a stats dict."""
    m = _stats_re.search(line)
    if not m:
        return None
    
    # Groups: 1=frame, 2=fps (optional), 3=size_val, 4=unit, 5=time, 6=bitrate, 7=speed
    try:
        frame = int(m.group(1))
        fps = float(m.group(2)) if m.group(2) else 0.0
        size_val = int(m.group(3))
        unit = m.group(4)
        time_str = m.group(5)
        bitrate = float(m.group(6))
        speed = float(m.group(7))

        if unit in ("MiB", "MB"):
            size_val *= 1024
        
        return {
            "frame": frame,
            "fps": fps,
            "size_kb": size_val,
            "time": time_str,
            "bitrate_kbps": bitrate,
            "speed": speed,
        }
    except (ValueError, IndexError):
        return None


def format_size_kb(kb: int) -> str:
    if kb < 1024:
        return f"{kb} KB"
    mb = kb / 1024
    if mb < 1024:
        return f"{mb:.1f} MB"
    return f"{mb / 1024:.1f} GB"
