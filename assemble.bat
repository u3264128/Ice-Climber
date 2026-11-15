@echo off
setlocal
python -X utf8 "%~dp0build.py" rom %*
exit /b %errorlevel%
