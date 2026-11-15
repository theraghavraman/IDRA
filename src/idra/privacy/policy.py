"""No arbitrary typed text; URL minimization and pre-storage pixel masks."""
from __future__ import annotations

import math
import re
from urllib.parse import urlsplit, urlunsplit

from idra.events.models import Payload, PrivacyConfig

_SECRET_PATTERNS = [
    re.compile(r"(?i)\b(?:bearer\s+)[A-Za-z0-9._~+/-]{8,}"),
    re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|AKIA[A-Z0-9]{16}|gh[pousr]_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35})\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    # Multiline PEM material (including malformed/unclosed blocks) is redacted as a unit.
    # This is applied after input length is bounded, so even a truncated key is removed.
    re.compile(r"-----BEGIN (?P<kind>(?:[A-Z0-9]+ )*PRIVATE KEY)-----[\s\S]*?"
               r"(?:-----END (?P=kind)-----|\Z)", re.IGNORECASE),
    re.compile(r"(?i)\b(?:postgres|postgresql|mysql|mongodb|redis|rediss)://[^\s,;]+"),
    re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key|token|access[_-]?key)\s*[:=]\s*[^\s,;]+"),
]

def redact_text(text: str) -> str:
    result = text[:4000]
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result

def sanitize_url(url: str, detail: str = "origin") -> str:
    if url == "about:blank":
        return url
    try:
        u = urlsplit(url)
        if u.scheme not in {"http", "https"} or not u.hostname:
            return "[REDACTED_URL]"
        host = u.hostname
        if ":" in host:
            host = f"[{host}]"
        if u.port is not None:
            host += f":{u.port}"
        path = u.path if detail == "path" else ""
        return urlunsplit((u.scheme, host, path, "", ""))[:2048]
    except ValueError:
        return "[REDACTED_URL]"

def sanitize_payload(payload: Payload, config: PrivacyConfig) -> Payload:
    result = payload.model_copy(deep=True)
    if result.url is not None:
        result.url = sanitize_url(result.url, config.url_detail)
    result.title = redact_text(result.title)[:256] if config.browser_titles and result.title else None
    result.label = redact_text(result.label)[:256] if config.browser_labels and result.label and not result.sensitive else None
    if result.text is not None:
        result.text = redact_text(result.text)
    return Payload.model_validate(result.model_dump())

def apply_masks(image, config: PrivacyConfig):
    # Work on a private array. Raw pixels are never written by this module.
    result = image.copy()
    height, width = result.shape[:2]
    for mask in config.masks:
        x0 = int(math.floor(mask.x * width))
        y0 = int(math.floor(mask.y * height))
        x1 = int(math.ceil((mask.x + mask.width) * width))
        y1 = int(math.ceil((mask.y + mask.height) * height))
        result[y0:y1, x0:x1] = 0
    return result

def safe_csv(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value
