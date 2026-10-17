# Daily export of the Weird Wall / Ledger figures into site/listen/, then commit and push.
# Consumer: brokenbranch.dev/listen/ via the site's daily mirror-pull. Registered in Task
# Scheduler at 06:00 local by Plan B Task B7 (not before Ben's go-live OK).
#
#   powershell -ExecutionPolicy Bypass -File scripts\daily_export.ps1 [-NoPush]
param([switch]$NoPush)
$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
$repo = Split-Path -Parent $PSScriptRoot
$py = 'E:\seti_staging\venv\Scripts\python.exe'
Set-Location $repo

& $py -m survey.figures_export --out site/listen/figures
if ($LASTEXITCODE -ne 0) { throw "figures_export failed ($LASTEXITCODE)" }

git add site/listen
git diff --cached --quiet -- site/listen
if ($LASTEXITCODE -eq 0) { Write-Output 'listen: nothing new today'; exit 0 }

$date = (Get-Date).ToUniversalTime().ToString('yyyy-MM-dd')
git commit -m "listen: daily export $date" -- site/listen
if ($LASTEXITCODE -ne 0) { throw "git commit failed ($LASTEXITCODE)" }
if (-not $NoPush) {
    git push
    if ($LASTEXITCODE -ne 0) { throw "git push failed ($LASTEXITCODE)" }
}
