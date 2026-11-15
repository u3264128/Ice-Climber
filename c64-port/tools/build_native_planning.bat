@echo off
setlocal
python -X utf8 "%~dp0..\..\build.py" native %*
exit /b %errorlevel%
