#!/bin/bash

# Build script for PartyStreamer (Windows Target)
# Note: This script assumes you are running in an environment 
# where cross-compilation or Windows compatibility layer is configured.
# Often requires running in a Windows VM or using Wine/Dockerized Windows build.

set -e

# Path to the Windows-compatible environment (or virtualenv)
# In a cross-compilation setup, this might be a path to a Windows-based python install
VENV_PATH="./.venv"
PYINSTALLER="$VENV_PATH/bin/pyinstaller"

echo "Cleaning previous build artifacts..."
rm -rf build/ dist/ *.spec

echo "Building Windows executable with PyInstaller..."
# Using --target-arch or simply relying on the Windows-based python/pyinstaller
"$PYINSTALLER" --noconfirm --onefile --windowed --name "PartyStreamer" \
  --add-data "resources;resources" \
  --collect-all "PyQt6" \
  --icon "resources/icons/app_icon.png" \
  main.py

echo "Build complete. Executable can be found in the 'dist' directory."
