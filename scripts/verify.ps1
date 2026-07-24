[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$InitialLocation = Get-Location
$ProjectRoot = Split-Path -Parent $PSScriptRoot

function Assert-Command {
    param(
        [Parameter(Mandatory)]
        [string]$Name
    )

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command was not found: $Name"
    }
}

function Invoke-ExternalCommand {
    param(
        [Parameter(Mandatory)]
        [string]$Label,

        [Parameter(Mandatory)]
        [string]$Command,

        [Parameter()]
        [string[]]$Arguments = @()
    )

    Write-Host ""
    Write-Host "==> $Label"
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE."
    }
}

try {
    Set-Location $ProjectRoot

    Write-Host "Project root: $ProjectRoot"
    Assert-Command -Name "uv"
    Assert-Command -Name "npm"
    Assert-Command -Name "git"

    Invoke-ExternalCommand `
        -Label "Sync Python dependencies" `
        -Command "uv" `
        -Arguments @("sync", "--frozen", "--extra", "web", "--extra", "dev")

    Invoke-ExternalCommand `
        -Label "Check version consistency" `
        -Command "uv" `
        -Arguments @("run", "python", ".\scripts\check_version.py", "--root", ".")

    Invoke-ExternalCommand `
        -Label "Run Ruff lint" `
        -Command "uv" `
        -Arguments @("run", "ruff", "check", ".")

    Invoke-ExternalCommand `
        -Label "Check Ruff formatting" `
        -Command "uv" `
        -Arguments @("run", "ruff", "format", "--check", ".")

    Invoke-ExternalCommand `
        -Label "Run pytest" `
        -Command "uv" `
        -Arguments @("run", "pytest", "-q")

    Set-Location (Join-Path $ProjectRoot "frontend")
    Invoke-ExternalCommand `
        -Label "Install frontend dependencies" `
        -Command "npm" `
        -Arguments @("ci")

    Invoke-ExternalCommand `
        -Label "Run frontend lint" `
        -Command "npm" `
        -Arguments @("run", "lint")

    Invoke-ExternalCommand `
        -Label "Run frontend tests" `
        -Command "npm" `
        -Arguments @("run", "test")

    Invoke-ExternalCommand `
        -Label "Build frontend" `
        -Command "npm" `
        -Arguments @("run", "build")

    Set-Location $ProjectRoot
    Invoke-ExternalCommand `
        -Label "Check Git whitespace" `
        -Command "git" `
        -Arguments @("diff", "--check")

    Write-Host ""
    Write-Host "Local verification completed successfully."
}
finally {
    Set-Location $InitialLocation
}
