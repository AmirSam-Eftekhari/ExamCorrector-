#!/usr/bin/env bash
# ============================================================
# ExamCorrector -- build a single-file binary (Linux/macOS)
#
# Run this ONCE on a machine with Python 3.11+ and internet access.
# It creates an isolated virtualenv, installs what's needed, and
# produces:
#
#     dist/ExamCorrector
#
# That single file is what you copy/share afterwards -- it does NOT
# need Python installed on the machine that runs it. Double-clicking
# / running it starts a local web server and opens your default
# browser to the ExamCorrector UI. It only listens on 127.0.0.1.
#
# NOTE: PyInstaller does not cross-compile. Running this on Linux
# produces a Linux binary; running it on macOS produces a macOS
# binary. For a Windows .exe, run build_exe.bat on a Windows machine.
#
# Templates and the database are saved next to the compiled binary
# so they persist between runs.
#
# You also need the `tesseract` binary installed and on PATH for
# text-field OCR (apt install tesseract-ocr / brew install tesseract).
# ============================================================
set -e

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 not found. Install Python 3.11+ first."
    exit 1
fi

echo "Creating build environment (.buildenv)..."
python3 -m venv .buildenv
source .buildenv/bin/activate

echo "Installing dependencies (this happens once)..."
pip install --upgrade pip >/dev/null
pip install opencv-python numpy Pillow pytesseract Flask pyinstaller

echo "Building ExamCorrector..."
pyinstaller --onefile --name ExamCorrector \
    --add-data "resources:resources" \
    --add-data "webapp/templates:webapp/templates" \
    --add-data "webapp/static:webapp/static" \
    --hidden-import webapp.server \
    main.py

echo
echo "============================================================"
echo " Done. Your executable is at: dist/ExamCorrector"
echo " Run it -- it opens your browser automatically."
echo "============================================================"
