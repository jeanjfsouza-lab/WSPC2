# PreToolUse hook for Edit/Write: refuses to write Unreal binary assets and generated folders.
# Reads the tool call as JSON on stdin; exit code 2 blocks the call and returns stderr to Claude.
$data = [Console]::In.ReadToEnd() | ConvertFrom-Json
$path = [string]$data.tool_input.file_path

if ($path -match '\.(uasset|umap)$' -or $path -match '(^|[\\/])(Binaries|Intermediate|DerivedDataCache)[\\/]') {
    [Console]::Error.WriteLine("Blocked: $path is a binary or generated file. Change content through a script in Tools/ or the editor.")
    exit 2
}

exit 0
