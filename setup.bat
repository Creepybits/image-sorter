@echo off
rem Creates a local venv and installs the requirements. Start.bat runs this for you on first start.
rem With an NVIDIA GPU it installs the CUDA build of torch (much faster); otherwise the CPU build.
where python >nul 2>&1 || (
    echo Python was not found. Install it from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH" in the installer, then run this again.
    if /i not "%~1"=="nopause" pause
    exit /b 1
)
python -m venv "%~dp0venv" || goto :failed
nvidia-smi >nul 2>&1 && "%~dp0venv\Scripts\python.exe" -m pip install torch --index-url https://download.pytorch.org/whl/cu124
"%~dp0venv\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt" || goto :failed
if /i not "%~1"=="nopause" pause
exit /b 0
:failed
echo Setup failed, see the messages above.
if /i not "%~1"=="nopause" pause
exit /b 1
