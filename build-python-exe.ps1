$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$source = Join-Path $root "src\traypocket.py"
$icon = Join-Path $root "assets\traypocket-icon.ico"
$buildDir = Join-Path $root "build\pyinstaller"
$distDir = Join-Path $root "dist"
$outputName = "TrayPocket-python-v0.3.5.exe"
$oneFileOutput = Join-Path $distDir "TrayPocket.exe"
$versionedOutput = Join-Path $distDir $outputName

if (-not (Test-Path $venvPython)) {
    throw "Virtual environment Python not found. Create .venv and install PyInstaller first."
}
if (-not (Test-Path $icon)) {
    throw "Application icon not found: $icon"
}

& $venvPython -m PyInstaller `
    --onefile `
    --windowed `
    --noconfirm `
    --clean `
    --icon $icon `
    --add-data "$icon;assets" `
    --name TrayPocket `
    --distpath $distDir `
    --workpath $buildDir `
    --specpath $buildDir `
    $source

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path $oneFileOutput)) {
    throw "Expected build output not found: $oneFileOutput"
}

Copy-Item -LiteralPath $oneFileOutput -Destination $versionedOutput -Force
Write-Host "Built $versionedOutput"
