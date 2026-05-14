"""Quality presets for ffmpeg streaming."""

PRESETS: dict[str, dict] = {
    "2160p": {
        "vb": "20000k",
        "scale": "scale=-1:2160",
        "ab": "320k",
        "preset": "fast",
    },
    "1440p": {
        "vb": "10000k",
        "scale": "scale=-1:1440",
        "ab": "256k",
        "preset": "fast",
    },
    "1080p": {
        "vb": "6000k",
        "scale": "scale=-1:1080",
        "ab": "192k",
        "preset": "fast",
    },
    "720p": {
        "vb": "2500k",
        "scale": "scale=-1:720",
        "ab": "128k",
        "preset": "fast",
    },
    "480p": {
        "vb": "1400k",
        "scale": "scale=-1:480",
        "ab": "96k",
        "preset": "fast",
    },
    "360p": {
        "vb": "800k",
        "scale": "scale=-1:360",
        "ab": "64k",
        "preset": "fast",
    },
    "Original": {
        "vb": "auto",
        "scale": None,
        "ab": "auto",
        "preset": "medium",
    },
}

DEFAULT_PRESET = "720p"
