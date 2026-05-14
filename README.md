# PartyStreamer

PartyStreamer is a powerful, PyQt6-based RTMP streaming application designed for seamless local video playback and high-quality live streaming. Built with Python 3.13 and FFmpeg, it offers a robust solution for streamers who need to broadcast local media content to platforms like YouTube, Twitch, or custom RTMP servers.

## Features

- **Integrated Media Playback:** Full-featured local video player with playback controls (Play, Pause, Stop, Seek).
- **High-Quality RTMP Streaming:** Stream local files with configurable resolution and quality presets.
- **Hardware Acceleration:** Automatic detection and utilization of hardware acceleration (NVENC for NVIDIA, VAAPI for Intel/AMD).
- **Intuitive UI:** A sleek, custom dark-themed interface built with PyQt6.
- **User-Friendly Experience:**
  - Drag-and-drop support for quick media loading.
  - Multi-track audio support.
  - Global hotkeys for playback management.
- **Advanced Monitoring:** Real-time stream statistics including bitrate.
- **Reliability:** Built-in auto-reconnect logic to handle unexpected FFmpeg interruptions.

## Architecture

PartyStreamer follows a modular design to ensure maintainability and performance:
- **UI Layer:** PyQt6-based interface components.
- **Core Engine:** Handles FFmpeg process management, hardware acceleration, and statistics parsing.
- **Threading:** Multi-threaded architecture ensures the UI remains responsive during streaming and parsing operations.

## Requirements

- Python 3.13+
- FFmpeg (either in system PATH or placed in the `ffmpeg/` directory)
- PyQt6

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/gddrx/partystreamer.git
   cd partystreamer
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/macOS
   # .venv\Scripts\activate  # Windows
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

Start the application:
```bash
python main.py
```

## Testing

Run the test suite using `pytest`:
```bash
pytest
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

Please note that this software is provided "as is," without warranty of any kind.
