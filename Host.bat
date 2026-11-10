@echo off
rem Hosts a game. The host drives; the first player to join becomes the gunner.
rem Other players connect to this PC's IP on UDP port 7777.
start "" "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe" "%~dp0WSPC2.uproject" /Game/VehicleTemplate/Maps/VehicleBasic?listen -game -log -windowed -ResX=1280 -ResY=720
