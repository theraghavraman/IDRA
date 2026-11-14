# Privacy, threat model and security controls

## Consent and scope

IDRA is intended for authorized, visible, local collection of computer-use demonstrations. Recording requires an explicit attestation of authorization and visible-content risk. It is not a monitoring daemon, employee-surveillance service or hidden keylogger. There is no auto-start, remote command channel, cloud upload, analytics SDK, clipboard reader or covert capture mode.

The GUI has continuously updated status and Stop controls; the CLI prints recording state and requires an operator to keep the recording terminal visible. Global stop requires enabled/trusted keyboard hooks. GUI indicators and native shortcut reliability must be checked on the target OS before deployment. Do not rely on an unverified hotkey as the sole privacy control.

## Data minimization by channel

**Keyboard:** Printable key identities/content are not collected. Events contain protected categories or finite special/modifier names. Capturing keyboard categories is off by default. Counts/timing can still reveal behavioral information and are sensitive telemetry.

**Browser:** Managed-context DOM instrumentation never reads form `.value`, clipboard, cookies or full DOM snapshots. All form inputs are sensitive; names/IDs and raw element attributes are not exported. Default URLs retain origins only; query, fragment and userinfo are stripped. Labels/titles and URL paths require explicit opt-in. These can contain private data and must be reviewed. Scripts are untrusted: the host validates an allowlist, finite metadata categories, length limits and event rate. Binding timestamps/outcomes are observations, not trustworthy task ground truth.

**Screen:** Video/screenshots capture pixels. Visible passwords, messages, account IDs and documents may appear even though keystroke and browser telemetry omit them. Configured fixed normalized masks are applied before encode/screenshot persistence. They do not dynamically track password boxes or identify all secrets. Pause before opening private content. Unreviewed media is excluded from dataset export by default; the media-review checkbox is a human attestation, not a detector.

**Annotations:** Explicit user notes/task descriptions are allowed. Known secret patterns are redacted, but no finite regex covers arbitrary passwords, personal data or encoded secrets. Keep real credentials out of annotations. Synthetic tests use clearly fake tokens solely to prove particular exclusion rules.

## Threat model

| Threat | Implemented control | Residual risk |
|---|---|---|
| Accidental sensitive input recording | No raw typed text/clipboard; sensitive form minimization; masks; explicit media review | Pixels, annotations, opt-in labels and timing can still reveal secrets |
| Malicious page supplying arbitrary payload | Host schema allowlist, field/category/size limits, rate limiting, no arbitrary text | A page can generate misleading allowed metadata; schema validity is not trust |
| Export path traversal or shell injection | Validated contained relative paths, UUID session paths, subprocess argument arrays, no shell interpolation | Hostile same-user filesystem races are outside the certified model |
| Crash or partial write | Append journals, fsync, staged manifests, advisory locks, recovery quarantine | Filesystem/controller power-loss guarantees and unreadable media remain limited |
| Tampered or stale index | Canonical-to-index comparison; checksum and reference validation | A coordinated rewrite of data plus manifest is not cryptographically authenticated |
| Unintended network transmission | No recorder upload client; ephemeral explicitly launched browser | Website traffic, system backup/sync clients and installed dependency behavior are separate |
| Unauthorized local file access | Private directories and files where supported | Same OS account/admin, malware, backups and permissive network filesystems can access data |

## Storage, logging, retention and deletion

Use a dedicated private, non-synchronized local folder and OS full-disk encryption where appropriate. Do not select a OneDrive/iCloud/Dropbox root for sensitive recordings unless external synchronization is explicitly intended and authorized. IDRA does not control those clients. Setting a directory private can alter permissions on that dedicated directory; do not select a shared system folder.

Application logs are separate from captured events and contain status/failure codes rather than event payloads. FFmpeg stderr logs remain inside private media/work directories and can contain filenames or codec diagnostics. Review them before sharing. No full environment dump, credential inventory or captured screen is added by normal diagnostics.

Retention is disabled by default. Preview eligible old sessions, then explicitly confirm deletion. Recovery/export/delete refuse active session locks. Deletion removes logical files; it does not certify secure erasure on SSDs, copy-on-write filesystems, snapshots, cloud sync or backups. Retain only what is authorized and document downstream dataset recipients separately.

## Supply chain and distribution

Direct versions are pinned, but a complete transitive hash lock and CVE audit are not provided. Review Python/native dependency sources and licenses before shipping. The source's MIT license does not replace PyQt's GPL/commercial obligations or FFmpeg/codec licenses. No signing/notarization, privileged installer, browser policy override or security-mechanism bypass is included.

The tests' root-only `--no-sandbox` flag is confined to disposable headless Chromium test launch options, not production defaults. It must not be copied into the normal application setup. Administrator-blocked network navigation is reported as skipped, not bypassed.

## v0.9.3 candidate browser-event provenance

Page scripts can call the managed Playwright browser binding. Managed-browser action
metadata is **unverified** even if the webpage submits `is_trusted: true`. The
controller removes that page-supplied claim and forces `outcome=observed_event_only`.
Trajectory quality includes `unverified_browser_actions` and
`browser_human_provenance_verified=false`. This is not a defense against synthetic
or malicious web actions; independent native input/frame corroboration or exclusion
from sensitive training pipelines remains necessary.

The global stop listener starts with an authorized real recording even when optional
key-category telemetry is off. Modifier state tracked for the stop chord is not
serialized into mouse events or keyboard events while category telemetry is disabled.
OS permission denial leaves the global stop unavailable; use the app Stop control
or CLI Ctrl+C in that situation.
