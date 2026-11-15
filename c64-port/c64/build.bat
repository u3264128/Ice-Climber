@echo off
setlocal
python -X utf8 "%~dp0..\..\build.py" build --demo %*
exit /b %errorlevel%
