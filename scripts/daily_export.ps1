# Daily export of the Weird Wall / Ledger figures into site/listen/, then commit and push.
# Consumer: brokenbranch.dev/listen/ via the site's daily mirror-pull (07:17 UTC). Registered
# in Task Scheduler by Plan B Task B7 (not before Ben's go-live OK), at a time that lands
# before 07:17 UTC so a day's figures reach the site the same day.
#
#   powershell -ExecutionPolicy Bypass -File scripts\daily_export.ps1 [-NoPush] [-NoExport]
#
# It runs unattended against a PUBLIC repo, so it refuses to push anything but its own
# kind of commit: it must be on main, and every commit main is ahead of origin/main by
# may touch site/listen/ only. A review note, a seal or a work-in-progress commit sitting
# on main stops the push (the export commit stays local) instead of going public at dawn.
# Best run from a dedicated clone that nobody works in.
param([switch]$NoPush, [switch]$NoExport)
$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
$repo = Split-Path -Parent $PSScriptRoot
$py = 'E:\seti_staging\venv\Scripts\python.exe'
Set-Location $repo

$branch = (git rev-parse --abbrev-ref HEAD).Trim()
if ($branch -ne 'main') { throw "daily export runs on main only (this checkout is on '$branch')" }

if (-not $NoExport) {
    & $py -m survey.figures_export --out site/listen/figures
    if ($LASTEXITCODE -ne 0) { throw "figures_export failed ($LASTEXITCODE)" }
}

git add site/listen
git diff --cached --quiet -- site/listen
if ($LASTEXITCODE -ne 0) {
    $date = (Get-Date).ToUniversalTime().ToString('yyyy-MM-dd')
    git commit -m "listen: daily export $date" -- site/listen
    if ($LASTEXITCODE -ne 0) { throw "git commit failed ($LASTEXITCODE)" }
} else {
    Write-Output 'listen: nothing new today'
}
if ($NoPush) { exit 0 }

git fetch --quiet origin main
if ($LASTEXITCODE -ne 0) { throw "git fetch failed ($LASTEXITCODE)" }
$ahead = @(git log --format= --name-only origin/main..HEAD | Where-Object { $_ -ne '' })
$outside = @($ahead | Where-Object { -not $_.StartsWith('site/listen/') })
if ($outside.Count -gt 0) {
    throw "refusing to push: commits ahead of origin/main touch files outside site/listen/: $($outside -join ', ')"
}
if ($ahead.Count -eq 0) { Write-Output 'listen: nothing to push'; exit 0 }
git push origin HEAD:main
if ($LASTEXITCODE -ne 0) { throw "git push failed ($LASTEXITCODE)" }
