"""CLI entry points are independently usable without importing Qt."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from uuid import uuid4

from idra.app.settings import load_settings, load_settings_safe
from idra.events.models import Payload, QualityThresholds, SegmentationConfig
from idra.storage.files import SessionLock, atomic_json, contained
from idra.storage.repository import Repository


def parser():
    p = argparse.ArgumentParser(prog="idra", description="Local-first, consent-based recording and dataset preparation")
    p.add_argument("--settings", type=Path)
    p.add_argument("--storage", type=Path)
    sub = p.add_subparsers(dest="command")
    sub.add_parser("gui", help="Launch the PyQt6 desktop application")
    d = sub.add_parser("diagnostics")
    d.add_argument("--probe-screen", action="store_true")
    d.add_argument("--consent", action="store_true")
    d.add_argument("--output", type=Path)
    r = sub.add_parser("record")
    r.add_argument("--consent", action="store_true", help="Attest authorization and accept visible-screen privacy risk")
    r.add_argument("--label", required=True)
    r.add_argument("--task", default="")
    r.add_argument("--seconds", type=float, default=0, help="0 records until Ctrl+C or global stop")
    r.add_argument("--no-mouse", action="store_true")
    r.add_argument("--keyboard", action="store_true")
    r.add_argument("--browser", action="store_true")
    r.add_argument("--url", default="about:blank")
    r.add_argument("--backend", choices=["mss", "ffmpeg_x11"])
    r.add_argument("--x11-display")
    r.add_argument("--region", help="left,top,width,height for the explicit X11 fallback")
    demo = sub.add_parser("demo", help="Generate a labeled synthetic fixture through the real media pipeline")
    demo.add_argument("--seconds", type=float, default=3)
    demo.add_argument("--export", type=Path)
    lib = sub.add_parser("list")
    lib.add_argument("--search", default="")
    lib.add_argument("--state", default="")
    lib.add_argument("--limit", type=int, default=500)
    lib.add_argument("--offset", type=int, default=0)
    sub.add_parser("summary", help="Aggregate library statistics across all recorded sessions")
    sub.add_parser("rescan", help="Reconcile the searchable library with on-disk manifests")
    show = sub.add_parser("inspect")
    show.add_argument("session_id")
    rec = sub.add_parser("recover")
    rec.add_argument("session_id")
    rec.add_argument("--confirm", action="store_true")
    delete = sub.add_parser("delete")
    delete.add_argument("session_id")
    delete.add_argument("--confirm", action="store_true")
    retain = sub.add_parser("retention")
    retain.add_argument("--days", type=int, required=True)
    retain.add_argument("--apply", action="store_true")
    retain.add_argument("--confirm", action="store_true")
    val = sub.add_parser("validate")
    val.add_argument("session_id")
    val.add_argument("--full-decode", action="store_true")
    val.add_argument("--strict-timing", action="store_true")
    val.add_argument("--max-gap", type=float, default=3)
    exp = sub.add_parser("export")
    exp.add_argument("session_ids", nargs="+")
    exp.add_argument("--out", type=Path, required=True)
    exp.add_argument("--include-media", action="store_true")
    exp.add_argument("--media-reviewed", action="store_true")
    exp.add_argument("--allow-incomplete", action="store_true")
    exp.add_argument("--split-unit", choices=["session", "task"], default="session")
    exp.add_argument("--ratios", default="0.8,0.1,0.1")
    exp.add_argument("--seed", default="idra-v1")
    exp.add_argument("--inactivity", type=float, default=30)
    exp.add_argument("--frame-stride", type=int, default=1)
    exp.add_argument("--navigation-boundaries", action="store_true")
    verify = sub.add_parser("verify-export")
    verify.add_argument("directory", type=Path)
    media = sub.add_parser("process")
    media.add_argument("session_id")
    media.add_argument("operation", choices=["inspect", "transcode", "clip", "extract"])
    media.add_argument("--out", type=Path)
    media.add_argument("--width", type=int)
    media.add_argument("--codec", default="libx264", choices=["libx264", "libx265", "mpeg4"])
    media.add_argument("--crf", type=int, default=20)
    media.add_argument("--start", type=float, default=0)
    media.add_argument("--duration", type=float, default=5)
    media.add_argument("--every-n", type=int, default=5)
    media.add_argument("--deduplicate", action="store_true")
    return p

def _print(value):
    print(json.dumps(value, indent=2, default=str, ensure_ascii=False))

def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        from idra.app.runtime import prepare_process
        prepare_process()
        command = args.command or "gui"
        warning = None
        if command == "gui":
            settings, warning = load_settings_safe(args.settings)
        else:
            settings = load_settings(args.settings)
        if args.storage:
            settings.storage_root = str(args.storage)
        if command == "gui":
            try:
                from idra.ui.window import launch
            except ImportError as exc:
                raise RuntimeError("GUI dependencies are unavailable. Install requirements.txt; PyQt6 is required.") from exc
            return launch(settings, settings_path=args.settings, warnings=[warning])
        if command == "diagnostics":
            if args.probe_screen and not args.consent:
                raise PermissionError("Use --consent to authorize capturing and discarding a diagnostic screen frame")
            from idra.diagnostics.checks import diagnose
            result = diagnose(settings, probe_screen=args.probe_screen)
            if args.output:
                atomic_json(args.output, result)
            _print(result)
            return int(any(c["status"] == "FAIL" for c in result["checks"]))
        if command == "verify-export":
            from idra.datasets.export import verify_export
            _print(verify_export(args.directory))
            return 0
        repository = Repository(settings.storage_root)
        if command in {"record", "demo"}:
            from idra.app.controller import SessionController
            from idra.capture.fixtures import SyntheticSource
            synthetic = command == "demo"
            if not synthetic and not args.consent:
                raise PermissionError("Recording requires --consent; visible content may include sensitive information")
            if args.seconds < 0 or (synthetic and not 0.2 <= args.seconds <= 60):
                raise ValueError("Use a nonnegative duration; synthetic demos must be between 0.2 and 60 seconds")
            if synthetic:
                settings.capture.capture_mouse = False
                settings.capture.capture_keyboard = False
                settings.capture.capture_window_context = False
                settings.browser.enabled = False
            else:
                settings.capture.capture_mouse = not args.no_mouse
                settings.capture.capture_keyboard = args.keyboard
                settings.browser.enabled = args.browser
                settings.browser.start_url = args.url
                if args.backend:
                    settings.capture.backend = args.backend
                if args.x11_display:
                    settings.capture.x11_display = args.x11_display
                if args.region:
                    left, top, width, height = [int(n) for n in args.region.split(",")]
                    settings.capture.region_left, settings.capture.region_top = left, top
                    settings.capture.region_width, settings.capture.region_height = width, height
            controller = SessionController(settings, repository)
            controller.start("SYNTHETIC demonstration" if synthetic else args.label,
                "Interact with a generated rectangle; synthetic observations only" if synthetic else args.task,
                consent=True, source=SyntheticSource() if synthetic else None, synthetic=synthetic)
            began, last_status, last_event = time.monotonic(), 0.0, 0.0
            print("SYNTHETIC FIXTURE" if synthetic else "RECORDING VISIBLE DESKTOP - Ctrl+C to stop", flush=True)
            try:
                while not controller.stop_requested.is_set():
                    elapsed = time.monotonic() - began
                    if args.seconds and elapsed >= args.seconds:
                        break
                    if synthetic and elapsed - last_event >= 0.3:
                        controller.emit("mouse_button_down", Payload(x=100, y=170, button="left", coordinate_space="desktop"), "synthetic")
                        last_event = elapsed
                    if elapsed - last_status >= 1:
                        status = controller.snapshot()
                        print(f"{status['state']} {elapsed:.1f}s frames={status['counts'].get('encoded_frames',0)} events={status['counts'].get('events',0)}", flush=True)
                        last_status = elapsed
                    time.sleep(0.05)
            except KeyboardInterrupt:
                print("Stopping and finalizing...", flush=True)
            finally:
                manifest = controller.stop()
            _print({"session_id":str(manifest.session_id), "state":manifest.state.value,
                    "directory":str(repository.path(manifest.session_id)), "counts":manifest.counts,
                    "failure_codes":manifest.failure_codes})
            if synthetic and args.export:
                from idra.datasets.export import export_dataset
                _print(export_dataset(repository, [manifest.session_id], args.export,
                                      include_media=True, media_reviewed=True))
            return int(manifest.state.value != "COMPLETED")
        if command == "list":
            _print(repository.list(args.search, limit=args.limit, offset=args.offset, state=args.state or None))
        elif command == "summary":
            _print(repository.summary())
        elif command == "rescan":
            _print(repository.scan())
        elif command == "inspect":
            _print(repository.load(args.session_id).model_dump(mode="json"))
        elif command == "recover":
            if not args.confirm:
                raise PermissionError("Recovery modifies partial journals and indexes; add --confirm")
            from idra.storage.recovery import recover
            _print(recover(repository, args.session_id))
        elif command == "delete":
            repository.delete(args.session_id, confirmed=args.confirm)
            _print({"deleted":args.session_id})
        elif command == "retention":
            rows = repository.retention_candidates(args.days)
            if args.apply:
                if not args.confirm:
                    raise PermissionError("Retention deletion requires both --apply and --confirm")
                for row in rows:
                    repository.delete(row["id"], confirmed=True)
            _print({"operation":"deleted" if args.apply else "preview", "sessions":rows})
        elif command == "validate":
            from idra.datasets.quality import validate_session
            result = validate_session(repository, args.session_id,
                QualityThresholds(max_gap_s=args.max_gap, strict_received_timing=args.strict_timing), full_decode=args.full_decode)
            _print(result)
            return int(result["errors"] > 0)
        elif command == "export":
            from idra.datasets.export import export_dataset
            config = SegmentationConfig(inactivity_s=args.inactivity, frame_stride=args.frame_stride,
                                        navigation_boundaries=args.navigation_boundaries)
            result = export_dataset(repository, args.session_ids, args.out, config=config,
                include_media=args.include_media, media_reviewed=args.media_reviewed,
                allow_incomplete=args.allow_incomplete, ratios=tuple(float(v) for v in args.ratios.split(",")),
                split_unit=args.split_unit, seed=args.seed)
            _print(result)
        elif command == "process":
            from idra.media.ffmpeg import inspect_video, transcode
            from idra.media.images import extract_frames
            directory = repository.path(args.session_id)
            with SessionLock(directory):
                manifest = repository.load(args.session_id)
                if not manifest.media:
                    raise ValueError("The session has no finalized canonical video")
                source = contained(directory, manifest.media)
                target = args.out or directory / "processed" / (uuid4().hex + ("" if args.operation == "extract" else ".mp4"))
                if args.operation == "inspect":
                    result = inspect_video(source, settings.ffprobe, count_frames=True)
                elif args.operation == "extract":
                    result = extract_frames(source, target, every_n=args.every_n, width=args.width,
                                            deduplicate=args.deduplicate, min_free_mb=settings.min_free_mb)
                else:
                    result = transcode(source, target, ffmpeg=settings.ffmpeg, ffprobe=settings.ffprobe,
                        width=args.width, codec=args.codec, crf=args.crf,
                        start_s=args.start if args.operation == "clip" else None,
                        duration_s=args.duration if args.operation == "clip" else None)
                repository.add_operation(args.session_id, args.operation, result)
                _print(result)
        return 0
    except Exception as exc:
        print(f"ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

def app_main() -> int:
    """Entry point of the packaged desktop app.

    With no arguments (double-click in Finder) it opens the GUI. Command-line use of the
    bundled executable, e.g. `IDRA.app/Contents/MacOS/IDRA diagnostics`, still works.
    Finder may append a process-serial-number argument (-psn_...), which is discarded.
    """
    argv = [a for a in sys.argv[1:] if not a.startswith("-psn_")]
    return main(argv or ["gui"])

if __name__ == "__main__":
    raise SystemExit(main())
