import logging
from datetime import datetime
from pathlib import Path
from pydantic import ValidationError
from idra.events.models import Settings
from idra.privacy.policy import sanitize_url
from idra.storage.files import atomic_json

logger = logging.getLogger("idra.settings")

def default_settings_path() -> Path:
    return Path.home() / ".idra" / "settings.json"

def load_settings(path: Path | None = None) -> Settings:
    path = path or default_settings_path()
    return Settings.model_validate_json(path.read_text()) if path.exists() else Settings()

def load_settings_safe(path: Path | None = None) -> tuple[Settings, str | None]:
    """Load settings for interactive start-up; an unreadable file never prevents launch.

    A damaged file is preserved beside the original (never deleted) and defaults are used.
    """
    path = path or default_settings_path()
    try:
        return load_settings(path), None
    except (OSError, ValueError, ValidationError) as exc:
        backup = path.with_name(f"{path.name}.unreadable-{datetime.now():%Y%m%d-%H%M%S}")
        try:
            path.replace(backup)
            where = f"The damaged file was kept as {backup}."
        except OSError:
            where = "The damaged file could not be moved and was left in place."
        logger.warning("settings_unreadable type=%s", type(exc).__name__)
        return Settings(), f"Your saved settings could not be read ({type(exc).__name__}), so defaults are in use. {where}"

def save_settings(settings: Settings, path: Path | None = None):
    data = settings.model_copy(deep=True)
    # Navigation targets can contain credentials in paths/queries. Persist only their origin.
    data.browser.start_url = sanitize_url(data.browser.start_url)
    atomic_json(path or default_settings_path(), data.model_dump(mode="json"))
