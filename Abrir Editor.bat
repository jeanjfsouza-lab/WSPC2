@echo off
rem Opens the WSPC2 project in the Unreal Editor, naming the project explicitly.
rem Use this (or double-click WSPC2.uproject) instead of starting the Unreal Editor on its own:
rem when the editor starts without a project and then auto-loads the last one, it fails to see the
rem compiled game module and asks for a rebuild that is not needed.
start "" "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe" "%~dp0WSPC2.uproject"
