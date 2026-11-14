# Run on Windows with your authorized publisher code-signing certificate.
# Produces signatures; does not imply commercial license or production approval.
param(
    [string]$AppDirectory = (Join-Path $PSScriptRoot '..\..\dist\IDRA'),
    [string]$CertThumbprint = $env:IDRA_SIGN_CERT_THUMBPRINT,
    [string]$TimestampUrl = 'http://timestamp.digicert.com'
)
$ErrorActionPreference = 'Stop'
if (-not $CertThumbprint) { throw 'Set IDRA_SIGN_CERT_THUMBPRINT for your publisher code-signing certificate.' }
$cert = Get-Item "Cert:\CurrentUser\My\$CertThumbprint" -ErrorAction Stop
if (-not $cert.HasPrivateKey) { throw 'Signing certificate private key is not available.' }
if ($cert.NotAfter -lt (Get-Date).AddDays(14)) { throw 'Certificate expires too soon for release.' }
$signTool = Get-Command signtool.exe -ErrorAction Stop
foreach ($name in @('IDRA.exe', 'idra-cli.exe')) {
    $file = Join-Path $AppDirectory $name
    if (-not (Test-Path -LiteralPath $file)) { throw "Missing native executable: $file" }
    & $signTool.Source sign /fd SHA256 /td SHA256 /tr $TimestampUrl /sha1 $CertThumbprint $file
    if ($LASTEXITCODE -ne 0) { throw "Signing failed: $name" }
    & $signTool.Source verify /pa /v $file
    if ($LASTEXITCODE -ne 0) { throw "Signature verification failed: $name" }
}
foreach ($name in @('install-idra.ps1', 'uninstall-idra.ps1')) {
    $file = Join-Path $PSScriptRoot $name
    $result = Set-AuthenticodeSignature -FilePath $file -Certificate $cert -HashAlgorithm SHA256 -TimestampServer $TimestampUrl
    if ($result.Status -ne 'Valid') { throw "Script signing failed: $name : $($result.Status)" }
    $verify = Get-AuthenticodeSignature -FilePath $file
    if ($verify.Status -ne 'Valid') { throw "Script signature validation failed: $name" }
}
Write-Host 'Authenticode verification passed on this Windows host.' -ForegroundColor Green
Write-Host 'Next: python packaging/build_app.py --package-only'
Write-Host 'Also preserve actual verification output, OS version, certificate identity and artifact SHA-256.'
