from datetime import datetime, timezone
from uuid import uuid4

import numpy as np
import pytest
from pydantic import ValidationError

from idra.app.state import transition
from idra.events.models import CaptureConfig, Consent, Event, Mask, Payload, PrivacyConfig, State
from idra.inputs.recorder import key_metadata
from idra.privacy.policy import apply_masks, redact_text, safe_csv, sanitize_payload, sanitize_url
from idra.synchronization.clock import SessionClock


def test_clock_keeps_monotonic_and_utc_origins():
    ticks = iter([10_000, 20_000, 40_000])
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = SessionClock(lambda: next(ticks), start)
    assert clock.now_ns() == 10_000
    assert clock.now_ns() == 30_000
    assert clock.utc_at(1_000_000_000).second == 1

@pytest.mark.parametrize("index,fps,expected", [(0,5,0), (3,5,600000000), (1,30,33333333)])
def test_nominal_media_time(index, fps, expected):
    assert SessionClock.media_pts_ns(index, fps) == expected

@pytest.mark.parametrize("index,fps", [(-1,5), (1,0), (0,-1)])
def test_invalid_media_time(index, fps):
    with pytest.raises(ValueError):
        SessionClock.media_pts_ns(index, fps)

def test_clock_detects_backwards_time():
    ticks = iter([100, 90])
    with pytest.raises(RuntimeError):
        SessionClock(lambda: next(ticks)).now_ns()

@pytest.mark.parametrize("url,expected", [
    ("https://user:pass@example.com/path?token=private#secret", "https://example.com"),
    ("http://localhost:8080/x?key=y", "http://localhost:8080"),
    ("https://[::1]:9443/a", "https://[::1]:9443"),
    ("file:///etc/passwd", "[REDACTED_URL]"),
    ("javascript:alert(1)", "[REDACTED_URL]"), ("about:blank", "about:blank")])
def test_url_minimization(url, expected):
    assert sanitize_url(url) == expected

def test_optional_path_drops_query_and_fragment():
    assert sanitize_url("https://example.com/visible?secret=1#private", "path") == "https://example.com/visible"

@pytest.mark.parametrize("text", ["password=not-public", "Bearer abcdefghijklmnop", "sk-abcdefghijklmnopqrst", "api_key = hiddenvalue"])
def test_known_secret_patterns(text):
    assert "[REDACTED]" in redact_text(text)

@pytest.mark.parametrize("name,expected", [(None, ("protected",None)), ("shift_l",("modifier","shift")),
    ("ctrl_r",("modifier","ctrl")), ("f8",("function","f8")), ("enter",("editing","enter")), ("home",("navigation","home"))])
def test_keyboard_normalization_never_reads_char(name, expected):
    class Key:
        @property
        def char(self):
            raise AssertionError("Raw characters must never be read")
    key = Key()
    key.name = name
    assert key_metadata(key) == expected

def test_protected_key_cannot_contain_identity():
    with pytest.raises(ValidationError):
        Payload(key_category="protected", key_name="enter")

@pytest.mark.parametrize("raw", [{"value":"secret"}, {"clipboard":"secret"}, {"raw_text":"secret"}, {"key_name":"a"}, {"redacted":False}])
def test_payload_fails_closed(raw):
    with pytest.raises(ValidationError):
        Payload.model_validate(raw)

def test_sensitive_label_is_removed_even_after_label_opt_in():
    p = Payload(label="private", sensitive=True, title="Private title", url="https://example.org/?token=x")
    safe = sanitize_payload(p, PrivacyConfig(browser_labels=True))
    assert safe.label is None and safe.title is None
    assert safe.url == "https://example.org"

def test_masks_do_not_mutate_raw_input():
    image = np.ones((20, 20, 3), np.uint8) * 127
    masked = apply_masks(image, PrivacyConfig(masks=[Mask(x=.5,y=0,width=.5,height=.5)]))
    assert (image == 127).all()
    assert (masked[:10,10:] == 0).all()
    assert (masked[10:] == 127).all()

@pytest.mark.parametrize("kwargs", [dict(x=.9,y=0,width=.2,height=.1), dict(x=-.1,y=0,width=.2,height=.1), dict(x=0,y=0,width=0,height=.1)])
def test_invalid_masks_rejected(kwargs):
    with pytest.raises(ValidationError):
        Mask(**kwargs)

@pytest.mark.parametrize("text", ["=1+1", "+SUM(A1:A2)", " @example", "-2+3"])
def test_csv_formula_defense(text):
    assert safe_csv(text).startswith("'")

def test_csv_numeric_value_is_unchanged():
    assert safe_csv(123) == 123

@pytest.mark.parametrize("pair", [(State.IDLE, State.STARTING), (State.RECORDING, State.PAUSED), (State.PAUSED,State.RECORDING), (State.STOPPING,State.COMPLETED)])
def test_allowed_state_transitions(pair):
    assert transition(*pair) == pair[1]

@pytest.mark.parametrize("pair", [(State.IDLE,State.COMPLETED), (State.RECORDING,State.COMPLETED), (State.COMPLETED,State.PAUSED)])
def test_invalid_state_transitions(pair):
    with pytest.raises(RuntimeError):
        transition(*pair)

def test_naive_utc_rejected():
    with pytest.raises(ValidationError):
        Event(session_id=uuid4(), sequence=0, t_ns=0, received_t_ns=0, utc=datetime(2026,1,1), type="annotation", source="controller")
    with pytest.raises(ValidationError):
        Consent(granted_at=datetime(2026,1,1), authorized_to_record=True, understands_visual_risk=True)

@pytest.mark.parametrize("display", ["host:0", "tcp://host:6000", ":0;rm -rf /", "../../test"])
def test_remote_or_malformed_displays_rejected(display):
    with pytest.raises(ValidationError):
        CaptureConfig(x11_display=display)


def test_expanded_secret_redaction_patterns():
    from idra.privacy.policy import redact_text
    sample = (
        "ghp_1234567890abcdefghijklmnopqrstuvwx "
        "xoxb-1234567890-abcdef "
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlMTIzNDU2 "
        "postgres://admin:supersecret@db.internal:5432/prod"
    )
    redacted = redact_text(sample)
    assert "ghp_" not in redacted
    assert "xoxb-" not in redacted
    assert "supersecret" not in redacted
    assert redacted.count("[REDACTED]") == 4


@pytest.mark.parametrize("kind", ["PRIVATE KEY", "RSA PRIVATE KEY", "EC PRIVATE KEY", "OPENSSH PRIVATE KEY"])
def test_complete_multiline_private_key_redaction(kind):
    private_material = "EXAMPLE_SECRET_MATERIAL_NON_REAL_12345678"
    raw = f"Before\n-----BEGIN {kind}-----\n{private_material}\n-----END {kind}-----\nAfter"
    cleaned = redact_text(raw)
    assert private_material not in cleaned
    assert "BEGIN" not in cleaned and "END" not in cleaned
    assert cleaned == "Before\n[REDACTED]\nAfter"


def test_truncated_or_unclosed_private_key_redacts_to_end():
    raw = "Note\n-----BEGIN PRIVATE KEY-----\n" + "REDACTABLE_KEY_BODY_" * 350
    cleaned = redact_text(raw)
    assert cleaned == "Note\n[REDACTED]"
