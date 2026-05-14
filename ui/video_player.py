from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QSlider, QLabel,
    QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget

from core.ffmpeg_path import get_logger


class VideoPlayerWidget(QWidget):
    """Video display with playback controls (play/pause/stop/seek +/-10/-30/+10/+30s)."""

    play_requested = pyqtSignal()
    pause_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    seek_requested = pyqtSignal(int)  # milliseconds

    def __init__(self, player: QMediaPlayer):
        super().__init__()
        self._logger = get_logger("VideoPlayerWidget")
        self._player = player
        self._duration = 0

        # Video display — 16:9 frame with letterbox
        self._video_frame = QFrame(objectName="videoFrame")
        frame_layout = QVBoxLayout(self._video_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        self._video_frame.setContentsMargins(0, 0, 0, 0)

        self._video_widget = QVideoWidget()
        self._video_widget.setStyleSheet("background-color: #000;")
        self._video_widget.setAspectRatioMode(Qt.AspectRatioMode.IgnoreAspectRatio)
        # Disable drops here so they bubble up to MainWindow
        self._video_widget.setAcceptDrops(False)
        self._video_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._player.setVideoOutput(self._video_widget)
        frame_layout.addWidget(self._video_widget)
        
        self.setAcceptDrops(False)

        self._video_frame.setMinimumSize(640, 360)
        self._video_frame.setFixedSize(960, 540)

        # Controls bar
        controls = QHBoxLayout()
        controls.setSpacing(8)

        self._btn_rewind30 = QPushButton("⏪ 30s")
        self._btn_rewind10 = QPushButton("⏪ 10s")
        self._btn_play = QPushButton("▶ Play")
        self._btn_play.setObjectName("btnPlay")
        self._btn_pause = QPushButton("⏸ Pause")
        self._btn_stop = QPushButton("⏹ Stop")
        self._btn_stop.setObjectName("btnStop")

        for btn in (self._btn_play, self._btn_pause, self._btn_stop):
            btn.setFixedSize(90, 36)

        self._btn_fwd10 = QPushButton("10s ⏩")
        self._btn_fwd30 = QPushButton("30s ⏩")

        for btn in (
            self._btn_rewind30, self._btn_rewind10, self._btn_play,
            self._btn_pause, self._btn_stop, self._btn_fwd10, self._btn_fwd30,
        ):
            btn.setFixedHeight(36)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            controls.addWidget(btn, stretch=0)

        # Position slider
        self._position_slider = QSlider(Qt.Orientation.Horizontal)
        self._position_slider.setRange(0, 1000)
        self._position_slider.setValue(0)
        self._position_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._position_slider.sliderMoved.connect(self._on_slider_moved)
        self._position_slider.sliderReleased.connect(self._on_slider_released)
        self._time_label = QLabel("00:00 / 00:00")
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._time_label.setFixedWidth(120)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(40, 0, 40, 0)
        bottom.addWidget(self._position_slider, stretch=1)
        bottom.addWidget(self._time_label)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self._video_frame, alignment=Qt.AlignmentFlag.AlignHCenter)
        main_layout.addLayout(controls)
        main_layout.addLayout(bottom)

        self.setMinimumSize(960, 620)  # 540 frame + controls + slider
        self.setMaximumWidth(960)
        self.setMaximumHeight(620)

        # Wire up buttons
        self._btn_play.clicked.connect(self.play_requested.emit)
        self._btn_pause.clicked.connect(self.pause_requested.emit)
        self._btn_stop.clicked.connect(self.stop_requested.emit)
        self._btn_rewind10.clicked.connect(self._rewind_10)
        self._btn_rewind30.clicked.connect(self._rewind_30)
        self._btn_fwd10.clicked.connect(self._forward_10)
        self._btn_fwd30.clicked.connect(self._forward_30)

        # Update position periodically
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(500)
        self._update_timer.timeout.connect(self._sync_position)
        self._update_timer.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def update_position(self, pos: int):
        self._current_pos = pos

    def update_duration(self, dur: int):
        self._duration = dur
        self._position_slider.setRange(0, dur)
        self._update_time_label(0, dur)

    def _update_time_label(self, pos: int, dur: int):
        self._time_label.setText(f"{self._fmt(pos)} / {self._fmt(dur)}")

    @staticmethod
    def _fmt(ms: int) -> str:
        total_sec = max(0, ms) // 1000
        m, s = divmod(total_sec, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def _on_slider_moved(self):
        """Update time display while dragging (no actual seek yet)."""
        val = self._position_slider.value()
        self._update_time_label(val, self._duration)

    def _on_slider_released(self):
        """Seek to slider position on release."""
        val = self._position_slider.value()
        self._logger.debug("Seek to %d ms", val)
        if self._player.playbackState() == QMediaPlayer.PlaybackState.StoppedState:
            self._player.pause()
        self._player.setPosition(val)
        self.seek_requested.emit(val)

    def _sync_position(self):
        """Update slider position from player (non-blocking)."""
        if self._position_slider.isSliderDown():
            return  # let user drag without jumping back
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            pos = self._player.position()
            self._position_slider.setValue(pos)
            self._update_time_label(pos, self._duration)

    def _rewind_10(self):
        self._logger.debug("Rewind 10s")
        self._seek_relative(-10000)

    def _rewind_30(self):
        self._logger.debug("Rewind 30s")
        self._seek_relative(-30000)

    def _forward_10(self):
        self._logger.debug("Forward 10s")
        self._seek_relative(10000)

    def _forward_30(self):
        self._logger.debug("Forward 30s")
        self._seek_relative(30000)

    def _seek_relative(self, delta: int):
        new_pos = max(0, self._player.position() + delta)
        new_pos = min(new_pos, self._duration)
        if self._player.playbackState() == QMediaPlayer.PlaybackState.StoppedState:
            self._player.pause()
        self._player.setPosition(new_pos)
        self.seek_requested.emit(new_pos)
