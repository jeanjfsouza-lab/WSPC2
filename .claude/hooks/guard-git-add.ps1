# PreToolUse hook for Bash/PowerShell: refuses bulk staging.
# About 22 GB of untracked asset packs sit in Content/ outside .gitignore; staging them would push all of it to LFS.
# Reads the tool call as JSON on stdin; exit code 2 blocks the call and returns stderr to Claude.
$data = [Console]::In.ReadToEnd() | ConvertFrom-Json
$cmd = [string]$data.tool_input.command

# "git", then any global options (-C <dir>, -c key=value, ...), then the subcommand
$git = 'git(\.exe)?\b[^|;&]*?\s'
$bulkAdd = $cmd -match ($git + 'add\b[^|;&]*\s(-A|--all|-u|--update|\.|\*|Content[\\/]?)(\s|$|;|&|\|)')
$commitAll = $cmd -cmatch ($git + 'commit\b[^|;&]*\s(-[b-zA-Z]*a[a-zA-Z]*|--all)(\s|$)')

if ($bulkAdd -or $commitAll) {
    [Console]::Error.WriteLine("Blocked: stage files by explicit path. Large untracked asset packs live in Content/.")
    exit 2
}

exit 0
