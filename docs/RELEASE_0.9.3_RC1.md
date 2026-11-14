# IDRA 0.9.3-rc1 - Release gate / acceptance ledger

**Classification: SOURCE-ONLY RELEASE CANDIDATE, NOT PRODUCTION ACCEPTED.**

## Corrective changes

| Audit issue | Implemented candidate change | Remaining gate |
|---|---|---|
| F-01 source inventory inconsistent | Repackage from final source with fresh per-file hashes | Reverify exact published ZIP and sign/attest digest |
| F-02 multiline private key leak | Redact PEM blocks with BEGIN/END and malformed tails | Extend adversarial coverage; review visual content separately |
| F-03 global emergency stop unavailable by default | Start a dedicated minimal stop listener in authorized real sessions, including when keyboard telemetry is disabled | Verify global OS hooks and permission denial on all target platforms; monitor visible availability |
| F-04 forged browser-action trust | Ignore page-supplied `is_trusted`, force `observed_event_only`, count unverified browser actions in trajectories | Independent human/desktop correlation remains unsolved; treat as low-trust for downstream AI |
| F-05 contradictory platform claims | Current candidate README and this matrix explicitly supersede historical claims | Collect native artifact-linked execution reports |
| F-06 commercial licenses and SBOM | Explicit gate retained | Counsel review, signed packages, SBOM, dependency and license audit |

## Native-platform evidence (current 0.9.3-rc1 candidate)

| Target | Status |
|---|---|
| Linux source automated tests and synthetic demo | Run in audit environment; see generated release verifier report |
| Linux bundled binary | Not rebuilt or executed for this candidate |
| Windows 10/11 x64 native application | Not built/tested in this environment |
| macOS arm64 native application | Not built/tested in this environment |
| macOS Intel x86_64 native application | Not built/tested in this environment |
| Linux Wayland desktop screen capture | Unsupported by current architecture |

## Product safeguards and limitations

- All recordings still require user authorization and explicit per-session consent.
- Global stop needs OS listener permissions; a failed *optional* listener is logged as unavailable.
- Keyboard telemetry remains disabled by default; the stop listener does not persist key events.
- Page-originated browser actions are unverified metadata, even when a page claims its DOM event
  was trusted. This change prevents incorrectly certifying trust; it does not stop a hostile page
  from submitting plausible-looking actions. Exclude or independently corroborate as needed.
- Static pixel masks do not dynamically redact sensitive content. Manual media review is still required.
- Dataset integrity checks verify references and checksums, not training suitability.

## Acceptance checklist before broad contributor / enterprise distribution

1. Exact v0.9.3 source inventory, extracted ZIP verifier, and published SHA-256 match; attest provenance.
2. Native GUI, live desktop input, keyboard-category-disabled emergency stop, screen and capture tests
   on each supported OS and architecture, including permission denials and multi-monitor DPI.
3. Packaged app `diagnostics -> demo -> export -> verify-export` plus authorized live capture.
4. Privacy adversarial tests (PEM, browser forgery, URL minimization, fixed masks, unintended raw text).
5. Multi-hour recording, recover-after-abrupt-termination, disk reserve and stress tests.
6. SBOM, commercial redistribution license approval (PyQt6/Qt/FFmpeg/Chromium included),
   dependency audit, signing/notarization/SmartScreen guidance and installer rollback.
7. Release owner signoff with artifact hashes, OS versions, executed tests and unresolved limitations.

**No production-readiness or native-platform guarantee is made by this source-only candidate.**
