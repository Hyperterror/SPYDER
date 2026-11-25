<#
.SYNOPSIS
    SPYDER-DETECT Backup Script for Windows Environments
#>
param(
    [string]$BackupRoot = ".\backups"
)

$ErrorActionPreference = "Stop"
$Stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$TargetDir = Join-Path $BackupRoot $Stamp
New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null

Write-Host "[1/3] Backing up database (PostgreSQL pg_dump or SQLite snapshot)..."
if ($env:DATABASE_URL -and $env:DATABASE_URL.StartsWith("postgresql")) {
    pg_dump $env:DATABASE_URL --format=custom --no-owner --file (Join-Path $TargetDir "postgres_spyder.dump")
} elseif (Test-Path ".\backend\spyder.db") {
    Copy-Item ".\backend\spyder.db" (Join-Path $TargetDir "spyder.db")
}

Write-Host "[2/3] Copying local evidence object store if present..."
if (Test-Path ".\backend\local_evidence_store") {
    Copy-Item -Recurse ".\backend\local_evidence_store" (Join-Path $TargetDir "local_evidence_store")
}

Write-Host "[3/3] Generating SHA-256 backup manifest..."
Get-ChildItem -Path $TargetDir -Recurse -File | Where-Object { $_.Name -ne "SHA256SUMS.txt" } | ForEach-Object {
    $hash = (Get-FileHash -Path $_.FullName -Algorithm SHA256).Hash.ToLower()
    $rel = $_.FullName.Substring((Resolve-Path $TargetDir).Path.Length + 1)
    "$hash  $rel"
} | Out-File -FilePath (Join-Path $TargetDir "SHA256SUMS.txt") -Encoding utf8

Write-Host "Backup completed: $TargetDir"
