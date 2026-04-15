#requires -version 5.1
<#
.SYNOPSIS
    Stop local dev listeners used by Trading Buddy (API, Vite, optional preview).
.DESCRIPTION
    Stops processes listening on the given TCP ports (default: 8000, 5173–5175, 4173).
    macOS/Linux 等价脚本：scripts/stop_dev.sh
    Then removes orphaned python multiprocessing workers whose parent PID no longer exists
    (common after killing uvicorn --reload while a worker remains).
    Uses OwningProcess / variable names that do not shadow the automatic $PID.
.EXAMPLE
    pwsh -File scripts/stop_dev.ps1
.EXAMPLE
    pwsh -File scripts/stop_dev.ps1 -Ports 8000,5173
#>
param(
    [int[]] $Ports = @(8000, 5173, 5174, 5175, 4173)
)

$ErrorActionPreference = 'SilentlyContinue'

foreach ($port in $Ports) {
    $conns = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
    foreach ($conn in $conns) {
        $listenPid = [int]$conn.OwningProcess
        if ($listenPid -le 0) { continue }
        Write-Host "Stopping PID $listenPid (port $port)"
        Stop-Process -Id $listenPid -Force -ErrorAction SilentlyContinue
    }
}

# Orphan uvicorn / multiprocessing workers: parent gone, child still alive (no longer listening on 8000).
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | ForEach-Object {
    $cmd = $_.CommandLine
    if (-not $cmd -or $cmd -notmatch 'spawn_main\(parent_pid=(\d+)') { return }
    $parentPid = [int]$Matches[1]
    $parentAlive = Get-Process -Id $parentPid -ErrorAction SilentlyContinue
    if (-not $parentAlive) {
        $childPid = [int]$_.ProcessId
        Write-Host "Stopping orphan multiprocessing worker PID $childPid (stale parent $parentPid)"
        Stop-Process -Id $childPid -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "Done. Verify: Get-NetTCPConnection -State Listen -LocalPort 8000,5173"
