import logging
import logging.handlers
import os
import shutil
import sys
import threading
import traceback

from core.version import VERSION


import datetime

def setup_logging(log_prefix: str = "partystreamer", level: int = logging.DEBUG):
    """Configure timestamped file + console logging for the PartyPlayer namespace."""
    
    log_dir = "logs"
    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir)
        except Exception:
            pass

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"{log_prefix}_{timestamp}.log")

    fmt = logging.Formatter(
        f"%(asctime)s [v{VERSION}] [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    
    # Still keep rotation within a single long-running session
    fh = logging.handlers.RotatingFileHandler(
        log_file, 
        encoding="utf-8", 
        maxBytes=5 * 1024 * 1024, 
        backupCount=3
    )
    fh.setFormatter(fmt)
    fh.setLevel(level)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    sh.setLevel(logging.INFO)

    root = logging.getLogger("PartyPlayer")
    root.setLevel(level)
    root.addHandler(fh)
    root.addHandler(sh)

    # Catch unhandled exceptions — write full traceback to log file
    crash_logger = logging.getLogger("PartyPlayer.CRASH")
    crash_logger.addHandler(fh)
    crash_logger.setLevel(logging.ERROR)

    _original_excepthook = sys.excepthook

    def _log_excepthook(exc_type, exc_value, exc_tb):
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        crash_logger.error("Unhandled exception:\n%s", tb_text)
        _original_excepthook(exc_type, exc_value, exc_tb)

    sys.excepthook = _log_excepthook

    def _log_thread_excepthook(args):
        tb_text = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
        crash_logger.error(
            "Unhandled exception in thread %s:\n%s",
            args.thread.name, tb_text,
        )

    threading.excepthook = _log_thread_excepthook


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger("PartyPlayer." + name)


def get_binary_path(name: str) -> str | None:
    """Resolve binary (ffmpeg or ffprobe): bundled local copy first, then system PATH."""
    logger = get_logger("binary_path")
    ext = ".exe" if sys.platform == "win32" else ""
    binary_name = name + ext
    
    # Try bundled binary for the current platform
    if sys.platform == "win32":
        platform_dir = "windows"
    elif sys.platform == "darwin":
        platform_dir = "macos"
    else:
        platform_dir = "linux"
        
    local_path = os.path.join(_project_root(), "ffmpeg", platform_dir, binary_name)

    if os.path.isfile(local_path):
        logger.debug("Found bundled %s: %s", name, local_path)
        return local_path

    sys_path = shutil.which(name)
    if sys_path:
        logger.debug("Found %s on PATH: %s", name, sys_path)
    else:
        logger.warning("%s not found", name)
    return sys_path


def get_ffmpeg_path() -> str | None:
    return get_binary_path("ffmpeg")


def get_ffprobe_path() -> str | None:
    return get_binary_path("ffprobe")


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
