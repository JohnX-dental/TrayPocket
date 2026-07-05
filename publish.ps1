param(
    [string]$Repo = "JohnX-dental/TrayPocket"
)

$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param(
        [scriptblock]$Command,
        [string]$ErrorMessage
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw $ErrorMessage
    }
}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI (gh) not found. Install it first: https://cli.github.com/"
}

Invoke-Checked { gh auth status } "GitHub CLI is not authenticated. Run: gh auth login"

if (-not (Test-Path ".git")) {
    throw "This directory is not a Git repository."
}

$branch = (git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($branch)) {
    throw "Cannot determine the current Git branch."
}

$remoteUrl = "https://github.com/$Repo.git"
$existingRemote = @(git remote)

gh repo view $Repo *> $null
$repoExists = $LASTEXITCODE -eq 0

if (-not $repoExists) {
    Invoke-Checked { gh repo create $Repo --public } "Failed to create GitHub repository: $Repo"
}

if ($existingRemote -contains "origin") {
    Invoke-Checked { git remote set-url origin $remoteUrl } "Failed to update origin remote."
} else {
    Invoke-Checked { git remote add origin $remoteUrl } "Failed to add origin remote."
}

Invoke-Checked { git push -u origin $branch } "Failed to push branch '$branch'."

Write-Host "Published: https://github.com/$Repo"
