import sys
import os
from PyQt6.QtWidgets import QApplication, QLineEdit
from PyQt6.QtCore import QObject, QEvent, Qt, QUrl, qInstallMessageHandler, QtMsgType
from PyQt6.QtGui import QIcon

from core.ffmpeg_path import setup_logging


class GlobalEventFilter(QObject):
    """
    Bulletproof global event interceptor. 
    Captures keys and drops before they reach any widget.
    """
    def __init__(self, window):
        super().__init__()
        self.window = window

    def eventFilter(self, obj, event):
        # 1. Global Drag & Drop
        if event.type() == QEvent.Type.DragEnter:
            if event.mimeData().hasUrls():
                event.acceptProposedAction()
                return True
        
        if event.type() == QEvent.Type.Drop:
            urls = event.mimeData().urls()
            if urls:
                path = urls[0].toLocalFile()
                ext = os.path.splitext(path)[1].lower()
                if ext in (".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"):
                    self.window._controls.set_file_path(path)
                    self.window._on_file_selected(path)
                    event.acceptProposedAction()
                    return True

        # 2. Global Hotkeys
        if event.type() == QEvent.Type.KeyPress:
            # Ignore if typing in an input field
            if isinstance(QApplication.focusWidget(), QLineEdit):
                return False
                
            key = event.key()
            if key == Qt.Key.Key_Space:
                self.window._toggle_playback()
                return True
            elif key == Qt.Key.Key_Left:
                self.window._video._rewind_10()
                return True
            elif key == Qt.Key.Key_Right:
                self._forward_10_safe()
                return True
                
        return super().eventFilter(obj, event)

    def _forward_10_safe(self):
        # Direct call to video widget's rewind logic
        if hasattr(self.window, "_video"):
            self.window._video._forward_10()


def _qt_message_handler(msg_type, context, message):
    if "QObject::disconnect" in message or "QFFmpeg" in message:
        return
    if msg_type in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg):
        sys.stderr.write(f"Qt: {message}\n")

def main():
    setup_logging()
    qInstallMessageHandler(_qt_message_handler)
    
    # Fix for Windows taskbar icon
    if sys.platform == 'win32':
        import ctypes
        myappid = 'mycompany.myproduct.subproduct.version' # arbitrary string
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    app = QApplication(sys.argv)
    app.setApplicationName("PartyPlayer")
    
    # Set global application icon
    icon_path = os.path.join(os.path.dirname(__file__), "resources", "icons", "app_icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    from ui.main_window import MainWindow
    window = MainWindow()
    
    # Install the 'Nuclear' filter on the entire app
    event_filter = GlobalEventFilter(window)
    app.installEventFilter(event_filter)
    
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
