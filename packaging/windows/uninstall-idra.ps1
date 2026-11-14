# Removes IDRA for the current user. Recordings (default: %USERPROFILE%\IDRA-recordings)
# and settings (%USERPROFILE%\.idra) are kept; delete them yourself if you no longer need them.
$ErrorActionPreference = 'Continue'
$target = Join-Path $env:LOCALAPPDATA 'Programs\IDRA'
if (Get-Process -Name 'IDRA' -ErrorAction SilentlyContinue) {
    Write-Host 'Close IDRA first, then run this again.' -ForegroundColor Red
    exit 1
}
foreach ($folder in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop'))) {
    Remove-Item -LiteralPath (Join-Path $folder 'IDRA.lnk') -Force -ErrorAction SilentlyContinue
}
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($userPath) {
    $kept = ($userPath -split ';' | Where-Object { $_ -and $_ -ne $target }) -join ';'
    [Environment]::SetEnvironmentVariable('Path', $kept, 'User')
}
Set-Location $env:TEMP
Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue
Write-Host 'IDRA was removed. Your recordings and settings were kept.' -ForegroundColor Green
