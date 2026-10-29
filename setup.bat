@echo off
rem Creates a local venv and installs the requirements. Run once.
rem For an NVIDIA GPU, install a CUDA build of torch first, e.g.:
rem   venv\Scripts\pip install torch --index-url https://download.pytorch.org/whl/cu124
python -m venv "%~dp0venv" || goto :end
"%~dp0venv\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt"
:end
pause
