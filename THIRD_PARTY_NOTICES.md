# Third-party dependencies and redistribution

The source archive does not bundle third-party Python wheels, Qt/FFmpeg binaries or font files. Its MIT license applies only to original IDRA source. Installing dependencies introduces their own licenses and obligations.

PyQt is available under GPL/commercial licensing; do not treat it as LGPL merely because some Qt components offer LGPL terms. Review Riverbank's actual license and obtain the appropriate authorization before distributing a proprietary app that embeds PyQt. Qt modules, Playwright/browser builds, OpenCV, NumPy, Pydantic, Pynput, MSS and their transitive packages have separate notices. FFmpeg builds and enabled codecs can have different license conditions; this implementation requires an encoder named libx264 but does not distribute it.

Primary references:
- https://www.riverbankcomputing.com/software/pyqt/
- https://www.riverbankcomputing.com/commercial/license-faq
- https://www.qt.io/licensing/
- https://ffmpeg.org/legal.html

A complete source/binary distribution license review, software bill of materials with transitive hashes, and vulnerability audit have not been completed for this source release. Native packaging is not provided. Review actual installed distributions rather than relying on these notes as a complete compliance determination.

## v0.9.3-rc2 release compliance hold

The declared library pins, Python-environment inventory, native binary components,
FFmpeg build, Qt plugins and optional Chromium distribution are NOT a legally reviewed
redistribution SBOM. The production release must include approved notices and applicable
source/licensing rights for the actual platform-specific package. See
`docs/PRODUCTION_RELEASE_RUNBOOK.md`. This candidate is source-only.
