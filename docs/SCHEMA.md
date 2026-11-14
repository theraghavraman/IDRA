# Versioned data and timestamp contract

Schema version is `1.0`; application version is `0.9.3`. Strict Pydantic source models reject unknown event/payload/frame/trajectory fields. Generated JSON Schemas in `docs/schemas/` describe those models. The portable dataset manifest is currently validated through explicit checks in `verify_export`, not a standalone generated Pydantic manifest model.

## Events

Each event contains a UUID `event_id`, `session_id`, ingestion `sequence`, monotonic elapsed `t_ns`, `received_t_ns`, timezone-aware UTC, type, source, timestamp kind, optional uncertainty, synthetic flag, and a constrained payload. Sequence is ingestion order, not a claim that asynchronous callbacks arrive in occurrence order. Exports read the index ordered by occurrence time and sequence; original journals retain arrival order.

Types: mouse_move, mouse_button_down/up, scroll, key_press/release, window_context, browser_navigation, browser_action, annotation, task_boundary, state_change, capture_gap. The implementation uses down/up events rather than synthesizing a separate click from every button pair. Browser click is an independently observed DOM event and may correlate with, but must not be silently deduplicated into, a native click.

Printable keyboard text, clipboard, character codes and arbitrary raw values have no supported schema fields. Printable keys are represented as `key_category=protected` with no key name. Special/modifier keys use finite categories/names. `payload.text` is reserved for explicit user annotations/task boundaries, not page scripts or native input.

Native pointer coordinates retain desktop coordinates and mapped captured-image pixels when available. Browser coordinates are viewport-relative and are **not equivalent to desktop pixels** without a separately observed window transform. Multi-monitor DPI mapping needs target-machine calibration; do not assert accuracy on an untested display configuration.

## Clock and media mapping

At session creation, a monotonic origin and timezone-aware UTC anchor are captured. `t_ns` is elapsed monotonic nanoseconds from that origin. UTC is derived from the anchor; later wall-clock changes do not reorder events. UTC precision is microseconds in Python datetime; elapsed integers retain nanosecond units without implying nanosecond physical accuracy.

A frame stores acquisition start, acquisition-complete or host receive timestamp, sequential encoded index, output dimensions, synthetic flag, nominal PTS, optional screenshot and SHA-256, redacted-pixel hash and blur score. The frame interval distinguishes acquisition latency from nominal playback time.

For configured FPS `f`, `pts_ns = floor(index * 1e9 / f)`. This is a **nominal CFR mapping**, not a copied native FFmpeg presentation timestamp. The MKV container quantizes timestamps. Use frame index to decode the corresponding video frame; use the journal's `t_ns` for session alignment. Paused time is not encoded; dropped frames are not invented. Thus a 30-second paused session can have substantially less than 30 seconds of playback. CLI clipping arguments refer to playback seconds, not session elapsed seconds.

Browser `performance.now()` is calibrated to host elapsed time using an observed round-trip midpoint. `uncertainty_ns` records half the measured round trip, not a universal error guarantee under arbitrary browser stalls. Uncalibrated events and the X11 pipe use `received` timestamps; strict timing validation can reject them. Native display/compositor acquisition accuracy is unverified.

## Trajectories

A trajectory has stable deterministic ID, session, user-provided task description, start/end elapsed timestamps, boundary reason, `task_completion`, synthetic flag, actions, annotation context and quality metadata. Each action references its original event and nearest available before/after frame within a three-second bound. `outcome=not_inferred` prevents invented successful actions. Browser navigation completion is an observed browser lifecycle event, not proof that the user's task succeeded.

Boundaries come from explicit task annotations, pauses/stops, inactivity, optional navigation, or bounded chunk size. Mouse moves alone do not create tasks. Continuation chunks retain the same `quality.task_group_id`. Frame-context sampling chooses indices, not rewritten timestamps. Annotation context is bounded; original annotations remain in the journal if context is truncated.

`task_completion=user_marked_complete` means only that the user marked a task end. It is not verified ground truth. Interrupted sessions never receive inferred success.

## Portable export

```text
manifest.json              sessions, settings/provenance, counts, checksums and split parameters
 events.jsonl              normalized events
 events.csv                spreadsheet-inspectable event rows with formula escaping
 frames.jsonl              frame metadata; media_available distinguishes metadata-only exports
 trajectories.jsonl        bounded action/context records
 splits.jsonl              trajectory -> train/validation/test assignments
 assets.jsonl              streaming media path/size/SHA-256 ledger
 sessions/<uuid>/quality.json
 sessions/<uuid>/media/...  present only after explicit media review
```

CSV retains JSON payload as one quoted column rather than destructively flattening variable event structures. Independent consumers can use JSONL/JSON without Qt or SQLite.

Split assignment hashes seed plus session ID or task group. Session-level splitting is the default leakage control. Task-level splitting may put related tasks from one session in different subsets and carries an explicit warning. Hashing is reproducible, not exact stratification: small datasets can have empty splits.

Re-import verification checks declared checksums/counts, strict event/frame/trajectory schemas, ID uniqueness, known sessions, action/frame references, split coverage and media integrity. Checksums detect accidental changes relative to a manifest; they are **not signatures** and do not defend against someone rewriting both data and manifest. Dataset suitability and consent for downstream use require separate review. Partial datasets with hard validation failures cannot be exported as clean datasets.
