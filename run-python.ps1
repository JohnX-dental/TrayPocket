$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$script = Join-Path $root "src\traypocket.py"

$pythonCandidates = @(
    (Join-Path $env:LOCALAPPDATA "Python\bin\pythonw.exe"),
    (Join-Path $env:LOCALAPPDATA "Python\bin\python.exe"),
    "pythonw.exe",
    "python.exe"
)

$python = $null
foreach ($candidate in $pythonCandidates) {
    $command = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($command -and $command.Source -notlike "*\Microsoft\WindowsApps\*") {
        $python = $command.Source
        break
    }
}

if (-not $python) {
    throw "Python was not found. Install Python 3.10+ from https://www.python.org/ first."
}

$argumentList = @("`"$script`"")
foreach ($arg in $args) {
    $argumentList += "`"$arg`""
}

Start-Process -FilePath $python -ArgumentList $argumentList
