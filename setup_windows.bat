@echo off
cd /d "%~dp0"
py -3.12 --version >nul 2>&1
if errorlevel 1 (set PYVER=3.11) else (set PYVER=3.12)
py -%PYVER% -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo Setup complete. Install Tesseract OCR separately for text recognition.
pause
