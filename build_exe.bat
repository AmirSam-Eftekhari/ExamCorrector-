@echo off
REM ============================================================
REM  ExamCorrector -- build a single-file ExamCorrector.exe
REM
REM  Run this ONCE on a Windows machine that has Python 3.11+
REM  installed (https://python.org -- tick "Add python.exe to PATH"
REM  during install). It creates an isolated environment, installs
REM  only what's needed, and produces:
REM
REM      dist\ExamCorrector.exe
REM
REM  That single file is what you copy/share afterwards -- it does
REM  NOT need Python installed on the machine that runs it.
REM
REM  Double-clicking it starts a local web server and opens your
REM  browser to the ExamCorrector UI automatically. Nothing leaves
REM  your machine -- it only listens on 127.0.0.1 (localhost).
REM
REM  Templates and the database are saved next to the .exe itself
REM  (in a "data" and "resources" folder created alongside it), so
REM  they persist between runs -- keep the .exe in its own folder
REM  rather than a temp/downloads folder you regularly clear out.
REM
REM  You still need Tesseract OCR installed separately for the
REM  Name/Class/Date text-field reading to work (bubble grading
REM  itself does not need it):
REM  https://github.com/UB-Mannheim/tesseract/wiki -- install it,
REM  then make sure tesseract.exe's folder is on your PATH.
REM ============================================================

setlocal

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found on PATH. Install it from https://python.org
    echo and re-run this script.
    pause
    exit /b 1
)

echo Creating build environment (.buildenv)...
python -m venv .buildenv
call .buildenv\Scripts\activate.bat

echo Installing dependencies (this happens once)...
pip install --upgrade pip >nul
pip install opencv-python numpy Pillow pytesseract Flask pyinstaller
if errorlevel 1 (
    echo Dependency installation failed -- check your internet connection.
    pause
    exit /b 1
)

echo Building ExamCorrector.exe (this can take a couple of minutes)...
pyinstaller --onefile --name ExamCorrector --console ^
    --add-data "resources;resources" ^
    --add-data "webapp/templates;webapp/templates" ^
    --add-data "webapp/static;webapp/static" ^
    --hidden-import webapp.server ^
    main.py

if errorlevel 1 (
    echo Build failed -- see the error above.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Done. Your executable is at:  dist\ExamCorrector.exe
echo  Copy that one file (keep it in its own folder) and double-
echo  click it -- it opens your browser automatically.
echo ============================================================
pause
