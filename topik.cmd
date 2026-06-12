@echo off
rem topik.cmd - TOPIK simulator launcher for double-click and cmd.exe use.
rem Forwards everything to topik.ps1 next to this file (see that script for
rem details). Keeps the console window open on errors so the message can be
rem read after a double-click launch.
setlocal

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0topik.ps1" %*

set TOPIK_EXIT=%ERRORLEVEL%
if %TOPIK_EXIT% geq 1 pause
exit /b %TOPIK_EXIT%
