@echo off
setlocal
python -X utf8 "%~dp0..\..\build.py" test || exit /b 1
python -X utf8 "%~dp0..\..\build.py" verify %*
exit /b %errorlevel%
