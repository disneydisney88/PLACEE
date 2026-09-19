# sync_drive.ps1 - PLACEE data/ mirror to Google Drive (G: virtual drive)
# Uses Google Drive desktop sync, no rclone OAuth needed.
# Manual: powershell -ExecutionPolicy Bypass -File scripts/sync_drive.ps1

$ErrorActionPreference = "Stop"
$src = Join-Path $PSScriptRoot "..\data"
$dstRoot = Get-ChildItem "G:\" -Directory |
    Where-Object { $_.Name -like "*我的雲端硬碟*" } |
    Select-Object -First 1
$log = Join-Path $PSScriptRoot "..\logs\sync_drive.log"
if (-not $dstRoot) {
    New-Item -ItemType Directory -Force -Path (Split-Path $log -Parent) | Out-Null
    Add-Content $log "$(Get-Date -Format s) SKIP: G: Drive folder not found"
    exit 0
}
$dst = Join-Path $dstRoot.FullName "PLACEE\data"
New-Item -ItemType Directory -Force -Path $dst, (Split-Path $log -Parent) | Out-Null
robocopy $src $dst /MIR /R:2 /W:5 /NFL /NDL | Out-Null
if ($LASTEXITCODE -le 7) {
    Add-Content $log "$(Get-Date -Format s) sync ok"
    exit 0
}
Add-Content $log "$(Get-Date -Format s) sync FAILED rc=$LASTEXITCODE"
exit 1
