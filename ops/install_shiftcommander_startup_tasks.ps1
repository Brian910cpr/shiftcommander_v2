$ErrorActionPreference = "Stop"

$RepoDir = "E:\GitHub\shiftcommander_v2"
$OpsDir = Join-Path $RepoDir "ops"
$LogsDir = Join-Path $OpsDir "logs"
$BackendBat = Join-Path $OpsDir "start_shiftcommander_backend.bat"
$TunnelBat = Join-Path $OpsDir "start_shiftcommander_tunnel.bat"

$BackendTaskName = "ShiftCommander Backend"
$TunnelTaskName = "ShiftCommander Cloudflare Tunnel"

New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

if (-not (Test-Path (Join-Path $RepoDir "server.py"))) {
    throw "server.py was not found at $RepoDir"
}
if (-not (Test-Path $BackendBat)) {
    throw "Missing $BackendBat"
}
if (-not (Test-Path $TunnelBat)) {
    throw "Missing $TunnelBat"
}

function Register-ShiftCommanderTask {
    param(
        [Parameter(Mandatory = $true)][string]$TaskName,
        [Parameter(Mandatory = $true)][string]$BatchPath,
        [Parameter(Mandatory = $true)][string]$LogPath
    )

    $command = "set SHIFTCOMMANDER_TASK_MODE=1&& call $BatchPath >> $LogPath 2>&1"
    $action = New-ScheduledTaskAction `
        -Execute "cmd.exe" `
        -Argument "/d /c ""$command""" `
        -WorkingDirectory $RepoDir
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Days 0) `
        -MultipleInstances IgnoreNew `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -StartWhenAvailable
    $principal = New-ScheduledTaskPrincipal `
        -UserId "$env:USERDOMAIN\$env:USERNAME" `
        -LogonType Interactive `
        -RunLevel Limited

    $task = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal
    Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null
}

Register-ShiftCommanderTask `
    -TaskName $BackendTaskName `
    -BatchPath $BackendBat `
    -LogPath (Join-Path $LogsDir "backend_task.log")

Register-ShiftCommanderTask `
    -TaskName $TunnelTaskName `
    -BatchPath $TunnelBat `
    -LogPath (Join-Path $LogsDir "tunnel_task.log")

Write-Host "Installed Scheduled Tasks:"
Write-Host "  $BackendTaskName"
Write-Host "  $TunnelTaskName"
Write-Host ""
Write-Host "Logs:"
Write-Host "  $(Join-Path $LogsDir "backend_task.log")"
Write-Host "  $(Join-Path $LogsDir "tunnel_task.log")"
Write-Host ""
Write-Host "Manual start commands:"
Write-Host "  Start-ScheduledTask -TaskName '$BackendTaskName'"
Write-Host "  Start-ScheduledTask -TaskName '$TunnelTaskName'"
