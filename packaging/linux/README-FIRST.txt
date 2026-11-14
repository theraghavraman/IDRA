IDRA 0.9.3 for Linux (prebuilt)
===============================

INSTALL (no sudo needed)
  tar -xzf IDRA-0.9.3-linux-*.tar.gz
  cd IDRA-0.9.3-linux-*
  ./install.sh
Then open IDRA from your applications menu, or run ~/.local/share/IDRA/IDRA.

REQUIREMENTS
  - x86_64 Linux with glibc 2.39 or newer (Ubuntu 24.04+, Debian 13+, Fedora 40+, current Arch).
    Older system? Build for your machine from the source package: ./build-idra-linux.sh
  - FFmpeg with libx264:  sudo apt install ffmpeg   (Fedora: dnf, Arch: pacman)
  - An X11 desktop session for recording. On Wayland (the default on Ubuntu and Fedora),
    choose the "Xorg" session on the login screen (gear icon) before recording.

FIRST USE
  Settings / diagnostics > "Run diagnostics". FFmpeg and the H.264 encoder should show PASS.
  Recordings are saved in ~/IDRA-recordings. Command line: idra --help

UNINSTALL
  ~/.local/share/IDRA/uninstall.sh   (recordings and settings are kept)

Full documentation: DOCUMENTATION.md in the source package.
