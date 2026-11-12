@echo off
rem Opens the WSPC2 project in the Unreal Editor with the built-in MCP server running,
rem so Claude Code can inspect and change the open project (see .mcp.json: http://localhost:8000/mcp).
rem The server only listens on this PC and stops when the editor closes.
start "" "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe" "%~dp0WSPC2.uproject" -ModelContextProtocolStartServer -ModelContextProtocolPort=8000
