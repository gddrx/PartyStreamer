import json
import os
import sys

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFileDialog, QCheckBox, QComboBox, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal

from core.quality_presets import PRESETS
from core.ffmpeg_path import get_logger

if sys.platform == "win32":
    _CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "partystreamer")
else:
    _CONFIG_DIR = os.path.expanduser("~/.config/partystreamer")

_URL_CONFIG_FILE = os.path.join(_CONFIG_DIR, "config.json")


class ControlsWidget(QWidget):
    """Top panel: file selector, RTMP URL input, quality selector, and status indicator."""

    file_selected   = pyqtSignal(str)
    quality_changed = pyqtSignal(str)
    osd_toggled     = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        
        # Ensure config directory exists
        os.makedirs(_CONFIG_DIR, exist_ok=True)
        
        # Save Timer to debounce disk I/O (must be initialized before any signal connections)
        from PyQt6.QtCore import QTimer
        self._save_timer = QTimer()
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(1000) # Save 1s after last change
        self._save_timer.timeout.connect(self._save_settings_to_disk)
        
        self._logger = get_logger("ControlsWidget")

        # Apply uniform compact style
        self.setStyleSheet(
            "QLabel { color: #e0e0e0; font-size: 12px; padding: 2px 0; }"
            "QLineEdit { background-color: #1a1a2e; color: #e0e0e0; padding: 4px 8px; "
            "border: 1px solid #0f3460; border-radius: 6px; min-height: 24px; max-height: 28px; }"
            "QCheckBox { color: #e0e0e0; font-size: 12px; padding: 2px 4px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Row 1: File selection
        file_row = QHBoxLayout()
        file_row.addWidget(QLabel("Video file:"))
        self._file_path = QLineEdit()
        self._file_path.setPlaceholderText("Select or Drag & Drop a video file...")
        self._file_path.setReadOnly(True)
        self._btn_browse = QPushButton("Browse...")
        self._btn_browse.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_browse.setStyleSheet(
            "QPushButton { background-color: #0f3460; color: #e0e0e0; padding: 4px 12px; "
            "border: none; border-radius: 6px; min-height: 24px; max-height: 28px; }"
            "QPushButton:hover { background-color: #1a4a7a; }"
        )
        file_row.addWidget(self._file_path, stretch=1)
        file_row.addWidget(self._btn_browse)

        # Row 2: URL + Key
        url_row = QHBoxLayout()
        url_row.addWidget(QLabel("Stream URL:"))
        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("rtmp:// server/app/streamkey")
        self._url_input.textChanged.connect(self._on_settings_changed)
        url_row.addWidget(self._url_input, stretch=1)

        url_row.addWidget(QLabel("API KEY:"))
        self._api_key_input = QLineEdit()
        self._api_key_input.setPlaceholderText("optional")
        self._api_key_input.textChanged.connect(self._on_settings_changed)
        url_row.addWidget(self._api_key_input, stretch=1)

        self._save_url_cb = QCheckBox("Save")
        self._save_url_cb.setChecked(True)
        self._save_url_cb.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        url_row.addWidget(self._save_url_cb)

        # Row 3: Quality
        qual_row = QHBoxLayout()
        qual_row.addWidget(QLabel("Quality:"))
        self._qual_buttons = {}
        self._selected_quality = "720p"

        for preset_name in PRESETS:
            preset_data = PRESETS[preset_name]
            btn = QPushButton(preset_name)
            btn.setCheckable(True)
            btn.setChecked(preset_name == "720p")
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda checked, name=preset_name: self._on_qual_button_clicked(name))
            
            vb = preset_data.get("vb", "auto")
            ab = preset_data.get("ab", "auto")
            btn.setToolTip(f"Video: {vb}\nAudio: {ab}\nEncoder: Auto")

            btn.setStyleSheet(
                "QPushButton { background-color: #16213e; color: #e0e0e0; padding: 4px 10px; "
                "border: 1px solid #0f3460; border-radius: 6px; min-height: 24px; max-height: 28px; "
                "font-size: 11px; font-weight: bold; }"
                "QPushButton:checked { background-color: #e94560; border-color: #e94560; }"
            )
            qual_row.addWidget(btn)
            self._qual_buttons[preset_name] = btn

        qual_row.addWidget(QLabel("OSD Time:"))
        self._osd_cb = QCheckBox()
        self._osd_cb.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._osd_cb.setToolTip("Show elapsed/remaining time overlay in stream")
        self._osd_cb.stateChanged.connect(self._on_osd_toggled)
        qual_row.addWidget(self._osd_cb)

        qual_row.addWidget(QLabel("Audio:"))
        self._audio_combo = QComboBox()
        self._audio_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._audio_combo.setFixedWidth(135)
        self._audio_combo.setStyleSheet(
            "QComboBox { background-color: #16213e; color: #e0e0e0; border: 1px solid #0f3460; "
            "border-radius: 6px; padding: 4px 8px; min-height: 24px; max-height: 28px; }"
            "QComboBox::drop-down { width: 0; border: none; }"
            "QComboBox::down-arrow { width: 0; height: 0; }"
            "QComboBox QAbstractItemView { background-color: #16213e; color: #e0e0e0; "
            "selection-background-color: #0f3460; border: 1px solid #0f3460; }"
        )
        self._audio_combo.currentIndexChanged.connect(self._on_settings_changed)
        qual_row.addWidget(self._audio_combo)

        qual_row.addStretch(1)

        # Status Indicator Frame
        self._status_frame = QFrame()
        self._status_frame.setStyleSheet(
            "QFrame { background-color: #16213e; border: 1px solid #0f3460; border-radius: 6px; }"
        )
        status_layout = QHBoxLayout(self._status_frame)
        status_layout.setContentsMargins(10, 0, 10, 0)
        status_layout.setSpacing(8)

        self._status_led = QLabel()
        self._status_led.setFixedSize(8, 8)
        self._status_led.setStyleSheet("background-color: #4a4a6a; border-radius: 4px; border: none;")
        
        self._status_label = QLabel("Status: idle")
        self._status_label.setStyleSheet("border: none; font-size: 11px; font-weight: bold; padding: 4px 0;")
        
        status_layout.addWidget(self._status_led)
        status_layout.addWidget(self._status_label)
        qual_row.addWidget(self._status_frame)

        layout.addLayout(file_row)
        layout.addLayout(url_row)
        layout.addLayout(qual_row)

        self._btn_browse.clicked.connect(self._browse_file)
        self._load_settings()

    def _load_settings(self):
        try:
            if os.path.isfile(_URL_CONFIG_FILE):
                with open(_URL_CONFIG_FILE, "r") as f:
                    data = json.load(f)
                self._url_input.setText(data.get("url", ""))
                self._api_key_input.setText(data.get("api_key", ""))
                last_qual = data.get("last_quality", "720p")
                if last_qual in self._qual_buttons:
                    self._on_qual_button_clicked(last_qual)
                self._osd_cb.setChecked(data.get("osd_time", False))
                
                last_path = data.get("last_file_path", "")
                if last_path and os.path.isfile(last_path):
                    self.set_file_path(last_path)
                    # Use a timer to emit signal after parent (MainWindow) is likely ready
                    from PyQt6.QtCore import QTimer
                    QTimer.singleShot(100, lambda: self.file_selected.emit(last_path))
        except Exception: pass

    def _on_settings_changed(self):
        # Trigger delayed save to disk
        self._save_timer.start()

    def _save_settings_to_disk(self):
        if self._save_url_cb.isChecked():
            try:
                self._logger.debug("Saving settings to disk...")
                data = {
                    "url": self._url_input.text().strip(),
                    "api_key": self._api_key_input.text().strip(),
                    "last_quality": self._selected_quality,
                    "last_audio_index": self._audio_combo.currentIndex(),
                    "osd_time": self._osd_cb.isChecked(),
                    "last_file_path": self._file_path.text().strip(),
                }
                with open(_URL_CONFIG_FILE, "w") as f: json.dump(data, f)
            except Exception: pass

    def set_file_path(self, path: str):
        self._file_path.setText(path)
        self._on_settings_changed()

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select video file", "", "Videos (*.mp4 *.mkv *.avi *.mov *.webm *.flv)")
        if path:
            self.set_file_path(path)
            self.file_selected.emit(path)

    def _on_qual_button_clicked(self, quality: str):
        self._selected_quality = quality
        for name, btn in self._qual_buttons.items():
            btn.setChecked(name == quality)
        self.quality_changed.emit(quality)
        self._on_settings_changed()

    def set_audio_tracks(self, tracks: list[dict]):
        self._audio_combo.blockSignals(True)
        self._audio_combo.clear()
        for track in tracks:
            self._audio_combo.addItem(track["description"], track["index"])
        try:
            if os.path.isfile(_URL_CONFIG_FILE):
                with open(_URL_CONFIG_FILE, "r") as f:
                    data = json.load(f)
                last_idx = data.get("last_audio_index", 0)
                if 0 <= last_idx < self._audio_combo.count():
                    self._audio_combo.setCurrentIndex(last_idx)
                else: self._audio_combo.setCurrentIndex(0)
        except Exception: self._audio_combo.setCurrentIndex(0)
        self._audio_combo.blockSignals(False)

    def set_status_text(self, text: str, state: str = "idle"):
        self._status_label.setText(text)
        color = "#4a4a6a" # idle
        if state == "streaming": color = "#00b894" # green
        elif state == "warning": color = "#fdcb6e" # yellow
        elif state == "error": color = "#e94560" # red
        self._status_led.setStyleSheet(f"background-color: {color}; border-radius: 4px; border: none;")

    def get_audio_index(self) -> int:
        return self._audio_combo.currentData() or 0

    def get_osd_enabled(self) -> bool:
        return self._osd_cb.isChecked()

    def get_url(self) -> str:
        url = self._url_input.text().strip()
        key = self._api_key_input.text().strip()
        return url.rstrip("/") + "/" + key if key else url

    def is_url_valid(self) -> bool:
        url = self.get_url()
        return url.lower().startswith(("rtmp://", "rtmps://"))

    def _on_osd_toggled(self, state: int):
        enabled = (state == Qt.CheckState.Checked.value)
        self.osd_toggled.emit(enabled)
        self._on_settings_changed()

    def get_quality(self) -> str:
        return self._selected_quality
