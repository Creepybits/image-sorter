@echo off
rem Sorts a folder of images into category folders (asks before moving).
rem Python is chosen in this order: %SORT_PYTHON%, a local venv (run setup.bat), python on PATH.
rem Extra arguments are passed on, e.g.  Sort_images.bat --dest E:\Sorted
if defined SORT_PYTHON (
    "%SORT_PYTHON%" -s "%~dp0sort_images.py" %*
) else if exist "%~dp0venv\Scripts\python.exe" (
    "%~dp0venv\Scripts\python.exe" "%~dp0sort_images.py" %*
) else (
    python "%~dp0sort_images.py" %*
)
pause
