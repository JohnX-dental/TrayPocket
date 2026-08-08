$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$dist = Join-Path $root "dist"
$zip = Join-Path $dist "TrayPocket-python-v0.3.5-windows.zip"

New-Item -ItemType Directory -Path $dist -Force | Out-Null

$files = @(
    (Join-Path $root "src\traypocket.py"),
    (Join-Path $root "assets\traypocket-icon.svg"),
    (Join-Path $root "assets\traypocket-icon.ico"),
    (Join-Path $root "assets\traypocket-icon-256.png"),
    (Join-Path $root "run-python.ps1"),
    (Join-Path $root "README.md"),
    (Join-Path $root "LICENSE"),
    (Join-Path $root "CHANGELOG.md"),
    (Join-Path $root "THIRD_PARTY_NOTICES.md")
)

Compress-Archive -LiteralPath $files -DestinationPath $zip -Force
Write-Host "Built $zip"
