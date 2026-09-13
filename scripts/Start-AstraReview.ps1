[CmdletBinding()]
param(
    [string]$RepoPath = (Split-Path -Parent $PSScriptRoot),
    [string]$Prompt = 'Continue ShiftCommander issue #214 in Brian910cpr/910cpr-class-landers. Read the full issue and latest dispatch before edits. Preserve dirty work, follow AGENTS.md and confirmed scheduling rules, and return a unique pushed root transport receipt. Do not deploy or change calendar authority.',
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$target = (Resolve-Path -LiteralPath $RepoPath).Path
$remote = (& git -C $target remote get-url origin).Trim()
if ($LASTEXITCODE -ne 0 -or $remote -notmatch '^(https://github\.com/|git@github\.com:)Brian910cpr/shiftcommander_v2(\.git)?$') {
    throw 'RepoPath must be the existing Brian910cpr/shiftcommander_v2 checkout.'
}
$branch = (& git -C $target branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -notlike 'codex/*') {
    throw 'Select an isolated named codex/ review branch before launching.'
}
$codex = (Get-Command codex.exe -ErrorAction Stop).Source

# Share the installed CyberPC dispatcher exclusion lock. Never overwrite its
# lease, heartbeat, or state. Holding this handle prevents a competing wake.
$wakeDirectory = Join-Path $env:LOCALAPPDATA '910CPR\CodexWake'
$lockPath = Join-Path $wakeDirectory 'worker.lock'
$leasePath = Join-Path $wakeDirectory 'state.json'
if (-not (Test-Path -LiteralPath $wakeDirectory -PathType Container)) {
    throw "Installed wake state directory is missing: $wakeDirectory"
}
$leaseLock = $null
$blocker = $null
try {
    try {
        $leaseLock = [System.IO.File]::Open($lockPath, 'OpenOrCreate', 'ReadWrite', 'None')
    } catch {
        $blocker = 'The dispatcher worker lock is held or inaccessible. Continue the active worker; do not launch a duplicate.'
    }
    if ($leaseLock -and (Test-Path -LiteralPath $leasePath)) {
        $lease = Get-Content -LiteralPath $leasePath -Raw | ConvertFrom-Json
        if ($lease.current_task -and $lease.last_dispatch_at -and
            (([datetimeoffset]::Now - [datetimeoffset]::Parse($lease.last_dispatch_at)).TotalMinutes -lt 90)) {
            $blocker = 'The dispatcher has an active 90-minute assignment lease. Continue that workstream first.'
        }
    }
    if ($CheckOnly) {
        [pscustomobject]@{
            timestamp = (Get-Date -Format o)
            requested_model = 'gpt-6-astra'
            repo = $target
            branch = $branch
            can_launch = ($null -eq $blocker)
            blocker = $blocker
            runtime_model_verified = $false
        } | ConvertTo-Json
        return
    }
    if ($blocker) { throw $blocker }
    & $codex -C $target -m gpt-6-astra $Prompt
    if ($LASTEXITCODE -ne 0) { throw "Codex exited with code $LASTEXITCODE; preserve the session and inspect its error before retrying." }
} finally {
    if ($leaseLock) { $leaseLock.Dispose() }
}
