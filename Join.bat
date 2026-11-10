@echo off
rem Joins a hosted game. Usage: Join.bat [host IP]   (no argument = this same PC, for testing)
set HOST=%1
if "%HOST%"=="" set HOST=127.0.0.1
start "" "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe" "%~dp0WSPC2.uproject" %HOST% -game -log -windowed -ResX=1280 -ResY=720
