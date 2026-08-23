param(
    [Parameter(Mandatory = $true, Position = 0, ValueFromRemainingArguments = $true)]
    [ValidateNotNullOrEmpty()]
    [string[]]$HostsOrIps
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

$MkcertArguments = @(
    "-cert-file", $CertificateFile,
    "-key-file", $KeyFile
) + $HostsOrIps + @("localhost", "127.0.0.1", "::1")

& mkcert @MkcertArguments

if ($LASTEXITCODE -ne 0) {
    throw "mkcert no pudo crear el certificado local."
}

$Urls = @($HostsOrIps | ForEach-Object { "https://${_}:5173" }) + "https://localhost:5173"
Write-Host ("Certificado creado para " + ($Urls -join ", "))
