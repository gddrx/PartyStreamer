#!/bin/bash

# Build script for PartyStreamer
# Uses PyInstaller to bundle the application into a single executable

set -e

# Path to the virtual environment
VENV_PATH="./.venv"
PYINSTALLER="$VENV_PATH/bin/pyinstaller"

echo "Cleaning previous build artifacts..."
rm -rf build/ dist/ *.spec

echo "Building executable with PyInstaller..."
"$PYINSTALLER" --noconfirm --onefile --windowed \
  --name "PartyStreamer" \
  --add-data "resources:resources" \
  --collect-all "PyQt6" \
  main.py

echo "Build complete. Executable can be found in the 'dist' directory."
