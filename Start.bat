@echo off
rem Double-click to open Image Sorter. The first time, it installs what it needs (a few GB, takes a while).
rem Python is chosen in this order: %SORT_PYTHON%, a local venv (created by setup.bat), python on PATH.
if defined SORT_PYTHON (
    set "PY=%SORT_PYTHON%"
) else (
    if not exist "%~dp0venv\Scripts\python.exe" (
        echo First start: installing what Image Sorter needs. This can take several minutes...
        call "%~dp0setup.bat" nopause || (pause & exit /b 1)
    )
    set "PY=%~dp0venv\Scripts\python.exe"
)
"%PY%" -c "import tkinter" >nul 2>&1 || (
    echo The window needs a Python that includes tkinter. The one in ComfyUI's python_embeded does not.
    echo Install Python from https://www.python.org/downloads/ or clear SORT_PYTHON, then try again.
    pause
    exit /b 1
)
rem pythonw runs without a black console window
start "" "%PY:python.exe=pythonw.exe%" "%~dp0sort_images_gui.py"
