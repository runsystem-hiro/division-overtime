[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Target,

    [Parameter()]
    [string]$RemoteRoot = "/home/pi/division-overtime"
)

$ErrorActionPreference = "Stop"
$InitialLocation = Get-Location
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ArchivePath = $null
$RemoteArchive = $null

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
    Assert-Command -Name "git"
    Assert-Command -Name "npm"
    Assert-Command -Name "ssh"
    Assert-Command -Name "scp"
    Assert-Command -Name "tar"

    $LocalVersion = (Get-Content -Raw (Join-Path $ProjectRoot "VERSION")).Trim()
    if ([string]::IsNullOrWhiteSpace($LocalVersion)) {
        throw "VERSION is empty."
    }

    $GitStatus = & git status --porcelain
    if ($LASTEXITCODE -ne 0) {
        throw "Git status check failed."
    }
    if ($GitStatus) {
        throw "Working tree is not clean. Commit, stash, or discard changes before frontend deployment."
    }

    $RemoteVersion = (& ssh $Target "cat '$RemoteRoot/VERSION'").Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to read the remote VERSION."
    }
    if ($RemoteVersion -ne $LocalVersion) {
        throw "Version mismatch: local=$LocalVersion remote=$RemoteVersion. Run the formal deploy.sh release flow first."
    }

    Set-Location (Join-Path $ProjectRoot "frontend")
    Invoke-ExternalCommand `
        -Label "Install frontend dependencies" `
        -Command "npm" `
        -Arguments @("ci")

    Invoke-ExternalCommand `
        -Label "Build frontend" `
        -Command "npm" `
        -Arguments @("run", "build")

    $DistPath = Join-Path $ProjectRoot "frontend/dist"
    if (-not (Test-Path (Join-Path $DistPath "index.html") -PathType Leaf)) {
        throw "frontend/dist/index.html was not created."
    }
    if (-not (Test-Path (Join-Path $DistPath "assets") -PathType Container)) {
        throw "frontend/dist/assets was not created."
    }

    $Stamp = Get-Date -Format "yyyyMMdd_HHmmss_fff"
    $ArchivePath = Join-Path ([System.IO.Path]::GetTempPath()) "division-overtime-frontend-$Stamp.tar.gz"
    $RemoteArchive = "/tmp/division-overtime-frontend-$Stamp.tar.gz"

    Invoke-ExternalCommand `
        -Label "Create frontend archive" `
        -Command "tar" `
        -Arguments @("-czf", $ArchivePath, "-C", $DistPath, ".")

    Invoke-ExternalCommand `
        -Label "Upload frontend archive" `
        -Command "scp" `
        -Arguments @($ArchivePath, "${Target}:$RemoteArchive")

    $RemoteScript = @'
set -euo pipefail

remote_root=$1
archive_path=$2
expected_version=$3
web_service="division-overtime-web.service"
health_url="http://127.0.0.1:8000/api/system/health"
stamp="$(date +%Y%m%d_%H%M%S_%N)"
frontend_root="$remote_root/frontend"
dist_dir="$frontend_root/dist"
staging_dir="$frontend_root/.dist-staging-$stamp"
backup_root="$remote_root/var/backups/frontend-dist"
backup_dir="$backup_root/$stamp"
failed_dir="$frontend_root/.dist-failed-$stamp"
health_file="/tmp/division-overtime-frontend-health-$stamp.json"

cleanup() {
    rm -f "$archive_path" "$health_file"
    rm -rf "$staging_dir"
}
trap cleanup EXIT

actual_version="$(cat "$remote_root/VERSION")"
if [[ "$actual_version" != "$expected_version" ]]; then
    echo "ERROR: remote version mismatch: expected=$expected_version actual=$actual_version" >&2
    exit 1
fi

mkdir -p "$staging_dir" "$backup_root"
tar -xzf "$archive_path" -C "$staging_dir"

if [[ ! -f "$staging_dir/index.html" || ! -d "$staging_dir/assets" ]]; then
    echo "ERROR: uploaded frontend archive is incomplete." >&2
    exit 1
fi

if [[ -d "$dist_dir" ]]; then
    mkdir -p "$backup_dir"
    mv "$dist_dir" "$backup_dir/dist"
fi

mv "$staging_dir" "$dist_dir"
sudo systemctl restart "$web_service"

for attempt in {1..15}; do
    if curl -fsS "$health_url" >"$health_file"; then
        deployed_version="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["version"])' "$health_file")"
        frontend_built="$(python3 -c 'import json, sys; print(str(json.load(open(sys.argv[1], encoding="utf-8"))["frontendBuilt"]).lower())' "$health_file")"
        if [[ "$deployed_version" == "$expected_version" && "$frontend_built" == "true" ]]; then
            cat "$health_file"
            echo
            find "$backup_root" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' \
                | sort -nr \
                | tail -n +6 \
                | cut -d' ' -f2- \
                | xargs -r rm -rf --
            echo "Frontend deployment completed. version=$deployed_version"
            exit 0
        fi
    fi
    sleep 1
done

echo "ERROR: frontend health check failed. Restoring the previous dist." >&2
sudo systemctl stop "$web_service"
mv "$dist_dir" "$failed_dir"
if [[ -d "$backup_dir/dist" ]]; then
    mv "$backup_dir/dist" "$dist_dir"
else
    echo "ERROR: no previous dist is available for rollback." >&2
    exit 1
fi
sudo systemctl start "$web_service"

for attempt in {1..15}; do
    if curl -fsS "$health_url" >"$health_file"; then
        cat "$health_file"
        echo
        echo "Previous frontend dist restored after deployment failure." >&2
        exit 1
    fi
    sleep 1
done

echo "ERROR: rollback completed, but the Web health check still failed." >&2
exit 1
'@

    Write-Host ""
    Write-Host "==> Activate frontend on Raspberry Pi"
    $RemoteScript | & ssh $Target "bash -s -- '$RemoteRoot' '$RemoteArchive' '$LocalVersion'"
    if ($LASTEXITCODE -ne 0) {
        throw "Remote frontend deployment failed with exit code $LASTEXITCODE."
    }

    Write-Host ""
    Write-Host "Frontend deployment completed successfully."
}
finally {
    if ($ArchivePath -and (Test-Path $ArchivePath)) {
        Remove-Item $ArchivePath -Force -ErrorAction SilentlyContinue
    }
    if ($RemoteArchive) {
        & ssh $Target "rm -f '$RemoteArchive'" 2>$null | Out-Null
    }
    Set-Location $InitialLocation
}
