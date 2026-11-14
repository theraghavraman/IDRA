# Transactional current-user IDRA installation.
# Files retain Mark-of-the-Web; production distribution requires signed artifacts.
$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot 'IDRA'
$parent = Join-Path $env:LOCALAPPDATA 'Programs'
$target = Join-Path $parent 'IDRA'
$stage = Join-Path $parent ('.IDRA-stage-' + [guid]::NewGuid().ToString('N'))
$backup = Join-Path $parent ('.IDRA-backup-' + [guid]::NewGuid().ToString('N'))
$oldMoved = $false
$activated = $false
$committed = $false

if (-not (Test-Path -LiteralPath (Join-Path $source 'IDRA.exe')) -or
    -not (Test-Path -LiteralPath (Join-Path $source 'idra-cli.exe'))) {
    throw 'Extract the complete Windows IDRA release archive before installing.'
}
if (Get-Process -Name 'IDRA', 'idra-cli' -ErrorAction SilentlyContinue) {
    throw 'Close IDRA and stop all active recordings before updating.'
}
New-Item -ItemType Directory -Path $parent -Force | Out-Null
try {
    Copy-Item -LiteralPath $source -Destination $stage -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'uninstall-idra.ps1') -Destination $stage -Force
    foreach ($name in @('IDRA.exe', 'idra-cli.exe')) {
        if (-not (Test-Path -LiteralPath (Join-Path $stage $name))) {
            throw "Staged distribution is incomplete: $name"
        }
    }
    if ($env:IDRA_REQUIRE_SIGNED_INSTALL -eq '1') {
        foreach ($name in @('IDRA.exe', 'idra-cli.exe')) {
            $signature = Get-AuthenticodeSignature -FilePath (Join-Path $stage $name)
            if ($signature.Status -ne 'Valid') {
                throw "Production signature verification failed for $name : $($signature.Status)"
            }
        }
    } else {
        Write-Warning 'Executable signatures have not been required/verified. This is not a production acceptance check.'
    }
    & (Join-Path $stage 'idra-cli.exe') --help | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Staged IDRA CLI failed compatibility check.' }

    if (Test-Path -LiteralPath $target) {
        Move-Item -LiteralPath $target -Destination $backup -ErrorAction Stop
        $oldMoved = $true
    }
    Move-Item -LiteralPath $stage -Destination $target -ErrorAction Stop
    $activated = $true

    $exe = Join-Path $target 'IDRA.exe'
    $shell = New-Object -ComObject WScript.Shell
    foreach ($folder in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop'))) {
        $link = $shell.CreateShortcut((Join-Path $folder 'IDRA.lnk'))
        $link.TargetPath = $exe
        $link.WorkingDirectory = $target
        $link.IconLocation = "$exe,0"
        $link.Description = 'IDRA - Intelligent Data Recording Agent'
        $link.Save()
    }
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    if (-not $userPath) { $userPath = '' }
    if (-not (($userPath -split ';') -contains $target)) {
        [Environment]::SetEnvironmentVariable('Path', (($userPath.TrimEnd(';')) + ';' + $target).TrimStart(';'), 'User')
    }
    $committed = $true
    if ($oldMoved) {
        try { Remove-Item -LiteralPath $backup -Recurse -Force -ErrorAction Stop }
        catch { Write-Warning "Prior installation backup still exists at $backup. Remove it manually after checking the new app." }
    }
} catch {
    Write-Warning "Installation failed: $_"
    if (-not $committed) {
        if ($activated) { Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue }
        if ($oldMoved) {
            try { Move-Item -LiteralPath $backup -Destination $target -ErrorAction Stop }
            catch { Write-Warning "Manual restore required from $backup to $target" }
        }
    }
    throw
} finally {
    if (Test-Path -LiteralPath $stage) {
        Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "IDRA installed at $target. Existing recordings and settings were preserved." -ForegroundColor Green
Write-Host 'Windows signing and SmartScreen reputation must be approved separately for production.'
if (-not (Test-Path (Join-Path $target '_internal\bin\ffmpeg.exe')) -and
    -not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Warning 'FFmpeg is unavailable; install Gyan.FFmpeg before recording.'
}
$answer = Read-Host 'Start IDRA now? [Y/n]'
if ($answer -notmatch '^[nN]') { Start-Process -FilePath (Join-Path $target 'IDRA.exe') -WorkingDirectory $target }
