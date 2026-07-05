$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $root "src\TrayPocket.cs"
$output = Join-Path $root "TrayPocket.exe"
$csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
$buildWorkDir = Join-Path ([System.IO.Path]::GetTempPath()) ("TrayPocket-build-" + [System.Guid]::NewGuid().ToString("N"))
$tempOutput = Join-Path $buildWorkDir "TrayPocket.exe"
$buildExitCode = 1

if (-not (Test-Path $csc)) {
    throw "C# compiler not found: $csc"
}

$running = Get-Process -Name "TrayPocket" -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -eq $output }

if ($running) {
    throw "TrayPocket.exe is running. Exit TrayPocket from the tray menu before rebuilding."
}

[System.IO.Directory]::CreateDirectory($buildWorkDir) | Out-Null
Push-Location $buildWorkDir
try {
    & $csc `
        /nologo `
        /target:winexe `
        /platform:anycpu `
        /optimize+ `
        /out:$tempOutput `
        /reference:System.dll `
        /reference:System.Core.dll `
        /reference:System.Drawing.dll `
        /reference:System.Windows.Forms.dll `
        $source

    $buildExitCode = $LASTEXITCODE
    if ($buildExitCode -eq 0) {
        Copy-Item -LiteralPath $tempOutput -Destination $output -Force
    }
}
finally {
    Pop-Location
    Remove-Item -LiteralPath $buildWorkDir -Recurse -Force -ErrorAction SilentlyContinue
}

if ($buildExitCode -ne 0) {
    throw "Build failed with exit code $buildExitCode"
}

Write-Host "Built $output"
