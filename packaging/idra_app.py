"""Frozen-application entry point (double-click opens the GUI; arguments run the CLI)."""
import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from idra.app.cli import app_main
    raise SystemExit(app_main())
