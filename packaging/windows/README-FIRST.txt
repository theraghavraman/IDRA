IDRA 0.9.3 for Windows 10/11 (x64)
==================================

INSTALL
  1. Extract this whole zip (right-click > Extract All). Do not run it from inside the zip.
  2. Double-click "Install IDRA.cmd".
     If Windows SmartScreen says "Windows protected your PC", click "More info" > "Run anyway".
     This appears because the app is not signed with a paid certificate; it is expected.
  3. Start IDRA from the Start menu or the desktop shortcut.

  No installer needed? Run IDRA\IDRA.exe directly from the extracted folder.

FIRST USE
  - Settings / diagnostics > "Run diagnostics": FFmpeg and the H.264 encoder should show PASS.
  - Windows needs no screen-recording permission. Some antivirus tools warn about apps that
    watch the mouse/keyboard; IDRA records key *categories* only, never typed characters.
  - Recordings are saved in %USERPROFILE%\IDRA-recordings.

COMMAND LINE
  idra-cli --help        (after installing; open a new terminal window)

UNINSTALL
  Run uninstall-idra.ps1 in %LOCALAPPDATA%\Programs\IDRA (right-click > Run with PowerShell).
  Recordings and settings are kept.

Full documentation: DOCUMENTATION.md in the source package.
