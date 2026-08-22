param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateNotNullOrEmpty()]
    [string]$HostOrIp
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command mkcert -ErrorAction SilentlyContinue)) {
    throw "No se encontró mkcert. Instálalo y ejecuta 'mkcert -install' primero."
}

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$CertificateDirectory = Join-Path $RepositoryRoot "certs"
$CertificateFile = Join-Path $CertificateDirectory "local.pem"
$KeyFile = Join-Path $CertificateDirectory "local-key.pem"

New-Item -ItemType Directory -Force -Path $CertificateDirectory | Out-Null

& mkcert `
    -cert-file $CertificateFile `
    -key-file $KeyFile `
    $HostOrIp localhost 127.0.0.1 "::1"

if ($LASTEXITCODE -ne 0) {
    throw "mkcert no pudo crear el certificado local."
}

Write-Host "Certificado creado para https://${HostOrIp}:8000"
