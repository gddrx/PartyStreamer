import os
from PyQt6.QtWidgets import (
    QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QLabel, QLineEdit, QComboBox, QFileDialog, QPushButton,
)
from PyQt6.QtCore import Qt, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QIcon
from PyQt6.QtMultimedia import QMediaPlayer

from core.ffmpeg_path import get_logger
from core.version import VERSION
from ui.video_player import VideoPlayerWidget
from ui.controls import ControlsWidget
from core.ffmpeg_controller import StreamController


DARK_THEME = """
QMainWindow { background-color: #1a1a2e; }
QWidget#central { background-color: #1a1a2e; }
QLabel { color: #e0e0e0; font-size: 13px; }
QLineEdit { background-color: #16213e; border: 1px solid #0f3460; border-radius: 6px; padding: 8px 12px; color: #e0e0e0; }
QLineEdit:focus { border: 1px solid #e94560; }
QPushButton { background-color: #16213e; border: 1px solid #0f3460; border-radius: 8px; padding: 10px 20px; color: #e0e0e0; font-weight: bold; }
QPushButton:hover { background-color: #0f3460; border: 1px solid #e94560; }
QPushButton#btnPlay { background-color: #00b894; border-color: #00b894; }
QPushButton#btnStop { background-color: #e94560; border-color: #e94560; }
QSlider::groove:horizontal { background: #16213e; height: 8px; border-radius: 4px; border: 1px solid #0f3460; }
QSlider::handle:horizontal { background: #e94560; width: 14px; height: 14px; margin: -3px 0; border-radius: 7px; }
QSlider::sub-page:horizontal { background: #0f3460; height: 8px; border-radius: 4px; }
"""


class MainWindow(QMainWindow):
    """Main application window."""
    _stats_signal  = pyqtSignal(dict)
    _error_signal  = pyqtSignal(str)
    _started_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._logger = get_logger("MainWindow")
        self.setWindowTitle("PartyPlayer — RTMP Streamer")
        
        # Set window icon
        icon_path = os.path.join(os.path.dirname(__file__), "..", "resources", "icons", "app_icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            
        self.resize(1050, 800)
        self.setMinimumHeight(780)
        self.setStyleSheet(DARK_THEME)
        
        # We don't need setAcceptDrops(True) here because main.py handles it globally
        
        self._video_path: str = ""
        self._selected_quality: str = "720p"
        self._video_duration: float = 0.0
        self._player = QMediaPlayer()

        self._stats_signal.connect(self._on_stats_safe, Qt.ConnectionType.QueuedConnection)
        self._error_signal.connect(self._on_stream_error_safe, Qt.ConnectionType.QueuedConnection)
        self._started_signal.connect(self._on_stream_started_safe, Qt.ConnectionType.QueuedConnection)
        
        self._stream = StreamController(
            on_stats=self._on_stats_emit,
            on_error=self._on_stream_error_emit,
            on_started=self._on_stream_started_emit,
        )

        central = QWidget(objectName="central")
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        self._controls = ControlsWidget()
        self._controls.file_selected.connect(self._on_file_selected)
        self._controls.quality_changed.connect(self._on_quality_changed)
        self._controls.osd_toggled.connect(self._on_osd_toggled)
        # Sync initial quality state after loading settings
        self._selected_quality = self._controls.get_quality()
        main_layout.addWidget(self._controls)

        self._video = VideoPlayerWidget(self._player)
        self._video.play_requested.connect(self._on_play)
        self._video.pause_requested.connect(self._on_pause)
        self._video.stop_requested.connect(self._on_stop)
        self._video.seek_requested.connect(self._on_seek)
        self._player.positionChanged.connect(self._video.update_position)
        self._player.durationChanged.connect(self._video.update_duration)
        self._player.durationChanged.connect(self._update_duration)
        main_layout.addWidget(self._video, alignment=Qt.AlignmentFlag.AlignHCenter)

        main_layout.addStretch()
        footer_layout = QHBoxLayout()
        version_label = QLabel(f"v{VERSION}")
        version_label.setStyleSheet("color: #4a4a6a; font-size: 11px;")
        footer_layout.addStretch()
        footer_layout.addWidget(version_label)
        main_layout.addLayout(footer_layout)

        self.setCentralWidget(central)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _update_duration(self, dur: int):
        self._video_duration = dur / 1000.0

    def _toggle_playback(self):
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._on_pause()
        else:
            self._on_play()

    def _on_file_selected(self, path: str):
        self._video_path = path
        self._player.setSource(QUrl.fromLocalFile(path))
        tracks = self._stream.get_audio_tracks(path)
        self._controls.set_audio_tracks(tracks)
        self._player.pause()

    def _on_quality_changed(self, quality: str):
        self._selected_quality = quality
        if self._stream.is_streaming:
            self._logger.info("Quality changed during stream. Restarting with new preset: %s", quality)
            self._on_play()

    def _on_osd_toggled(self, enabled: bool):
        self._logger.info("OSD toggled in UI: enabled=%s, stream_active=%s", enabled, self._stream.is_streaming)
        if self._stream.is_streaming:
            self._logger.info("Restarting stream due to OSD toggle.")
            self._on_play()

    def _on_play(self):
        url = self._controls.get_url()
        if not self._video_path:
            self._controls.set_status_text("Error: select a video file", "warning")
            return
        
        if not url:
            self._controls.set_status_text("Error: enter RTMP URL", "warning")
            return

        if not self._controls.is_url_valid():
            self._controls.set_status_text("Error: invalid URL (must start with rtmp://)", "error")
            return
        
        # Don't play local player yet — wait for stream to start
        pos = self._player.position() / 1000.0
        audio_idx = self._controls.get_audio_index()
        osd = self._controls.get_osd_enabled()
        self._stream.start(url, self._video_path, self._selected_quality, pos, audio_idx, osd, self._video_duration)
        self._controls.set_status_text("Status: starting stream...", "warning")

    def _on_pause(self):
        self._player.pause()
        self._stream.stop()
        self._controls.set_status_text("Status: paused", "idle")

    def _on_stop(self):
        self._player.stop()
        self._stream.stop()
        self._controls.set_status_text("Status: stopped", "idle")

    def _on_seek(self, pos: float):
        if self._stream.is_streaming:
            # When seeking during stream, pause local player until stream catches up
            self._player.pause()
            url = self._controls.get_url()
            audio_idx = self._controls.get_audio_index()
            osd = self._controls.get_osd_enabled()
            self._stream.seek(url, self._video_path, self._selected_quality, pos / 1000.0, audio_idx, osd, self._video_duration)

    def _on_stats_emit(self, stats: dict):
        self._stats_signal.emit(stats)

    @pyqtSlot(dict)
    def _on_stats_safe(self, stats: dict):
        self._controls.set_status_text(
            f"Status: streaming · {stats['bitrate_kbps']:.0f} kbps",
            "streaming"
        )

    def _on_stream_error_emit(self, msg: str):
        self._error_signal.emit(msg)

    @pyqtSlot(str)
    def _on_stream_error_safe(self, msg: str):
        self._controls.set_status_text(f"Status: error — {msg}", "error")

    def _on_stream_started_emit(self):
        self._logger.debug("Emitting _started_signal.")
        self._started_signal.emit()

    @pyqtSlot()
    def _on_stream_started_safe(self):
        self._logger.info("Stream started signal received in UI. Scheduling self._player.play().")
        # Add a tiny delay to prevent hardware acceleration conflicts that cause SIGSEGV
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(200, self._safe_play)
        self._controls.set_status_text("Status: streaming", "streaming")

    def _safe_play(self):
        try:
            if self._player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self._logger.debug("Executing safe play command.")
                self._player.play()
        except Exception as e:
            self._logger.error("Failed to start local playback: %s", e)

    def closeEvent(self, event):
        self._logger.info("Closing main window, stopping stream.")
        self._stream.stop(cancel_reconnect=True)
        # Give a small window for the thread to cleanup
        import time
        time.sleep(0.1)
        super().closeEvent(event)
