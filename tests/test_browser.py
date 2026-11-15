import functools
import http.server
import json
import os
import shutil
import threading
import time

import pytest

from idra.app.controller import SessionController
from idra.browser.managed import Instrumentation, ManagedBrowser
from idra.capture.fixtures import SyntheticSource
from idra.events.models import BrowserConfig, PrivacyConfig
from idra.privacy.policy import sanitize_payload
from idra.storage.files import iter_jsonl
from idra.synchronization.clock import SessionClock

pytestmark = pytest.mark.browser


@pytest.fixture
def web_page(tmp_path):
    html = """<!doctype html><html><head><title>PRIVATE_TITLE_NOT_DEFAULT</title></head>
    <body><h1>Explicit synthetic browser fixture</h1>
    <button aria-label="Synthetic action" id="button">Run fixture</button>
    <input id="password" type="password" aria-label="SENSITIVE_LABEL">
    <input id="normal" type="text"><a id="next" href="/second.html?secret=fixture#secret">Next</a>
    <div style="height:3000px">Synthetic scroll surface</div></body></html>"""
    (tmp_path / "index.html").write_text(html)
    (tmp_path / "second.html").write_text("<html><body>Second synthetic page</body></html>")
    (tmp_path / "auto.html").write_text("""<!doctype html><html><body>
    <button id="b">Synthetic action</button><input type="password" id="p">
    <script>setTimeout(()=>{document.querySelector('#b').click();
    const p=document.querySelector('#p');p.value='FAKE_PASSWORD_FOR_TEST';
    p.dispatchEvent(new Event('input',{bubbles:true}));},700);</script></body></html>""")

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    handler = functools.partial(QuietHandler, directory=str(tmp_path))
    server = None
    worker = None
    url = None
    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        url = f"http://127.0.0.1:{server.server_address[1]}"
    except OSError:
        server = None
    try:
        yield {"url": url, "html": html, "auto": (tmp_path / "auto.html").read_text()}
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if worker is not None:
            worker.join(3)


def load_fixture(page, html):
    # Real in-memory Chromium DOM. Avoid document.open(), which removes init-script listeners.
    page.evaluate(
        """html => {
        document.documentElement.innerHTML = html;
        document.querySelectorAll('script').forEach(old => {
            const script=document.createElement('script');script.textContent=old.textContent;
            old.replaceWith(script);
        });
    }""",
        html,
    )


def launch_options():
    exe = (
        os.getenv("IDRA_TEST_CHROMIUM")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
    )
    args = ["--no-sandbox"] if hasattr(os, "geteuid") and os.geteuid() == 0 else []
    # This flag is solely for a disposable root-owned headless test container, never app defaults.
    return {"headless": True, "args": args, **({"executable_path": exe} if exe else {})}


@pytest.fixture
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            b = p.chromium.launch(**launch_options())
        except Exception as e:
            pytest.skip("Real Chromium unavailable: " + type(e).__name__)
        try:
            yield b
        finally:
            b.close()


def test_real_browser_actions_never_include_form_values(browser, web_page):
    privacy = PrivacyConfig()
    seen = []

    def emit(kind, payload, source, **timing):
        seen.append(
            {
                "type": kind,
                "payload": sanitize_payload(payload, privacy).model_dump(mode="json"),
                **timing,
            }
        )

    context = browser.new_context(viewport={"width": 800, "height": 600})
    ins = Instrumentation(context, emit, SessionClock(), privacy)
    page = context.new_page()
    load_fixture(page, web_page["html"])
    ins.calibrate(page.main_frame)
    page.locator("#button").click()
    page.locator("#password").fill("FAKE_PASSWORD_FOR_TEST")
    page.locator("#normal").fill("PRIVATE_NORMAL_TEXT")
    page.mouse.wheel(0, 700)
    page.wait_for_timeout(250)
    encoded = json.dumps(seen)
    assert "FAKE_PASSWORD_FOR_TEST" not in encoded
    assert "PRIVATE_NORMAL_TEXT" not in encoded
    assert "URL_SECRET" not in encoded and "FRAGMENT_SECRET" not in encoded
    assert "PRIVATE_TITLE_NOT_DEFAULT" not in encoded
    assert "SENSITIVE_LABEL" not in encoded
    actions = [e for e in seen if e["type"] == "browser_action"]
    assert {"click", "input", "scroll"} <= {e["payload"]["action"] for e in actions}
    assert any(
        e["payload"]["sensitive"] and e["payload"]["input_type"] == "password" for e in actions
    )
    assert all(e["payload"]["redacted"] for e in actions)
    assert any(e.get("timestamp_kind") == "calibrated" for e in actions)
    assert ins.counts["actions"] == len(actions)
    context.close()


def test_browser_optin_labels_exclude_sensitive_fields(browser, web_page):
    privacy = PrivacyConfig(browser_labels=True)
    seen = []

    def emit(kind, payload, source, **kw):
        seen.append(sanitize_payload(payload, privacy))

    context = browser.new_context()
    Instrumentation(context, emit, SessionClock(), privacy)
    page = context.new_page()
    load_fixture(page, web_page["html"])
    page.locator("#button").click()
    page.locator("#password").fill("NOT_STORED")
    page.wait_for_timeout(150)
    assert any(p.label == "Synthetic action" for p in seen)
    assert all(p.label is None for p in seen if p.sensitive)
    context.close()


def test_untrusted_page_binding_cannot_inject_text(browser, web_page):
    privacy = PrivacyConfig()
    seen = []
    context = browser.new_context()
    ins = Instrumentation(context, lambda *a, **kw: seen.append(a), SessionClock(), privacy)
    page = context.new_page()
    load_fixture(page, web_page["html"])
    before = len(seen)
    page.evaluate(
        "window.__idra_event({action:'input',text:'MALICIOUS_EXFILTRATION',redacted:true})"
    )
    assert len(seen) == before
    assert ins.counts["rejected"] >= 1
    context.close()


def test_pause_suppresses_browser_events(browser, web_page):
    privacy = PrivacyConfig(url_detail="path")
    seen = []
    active = [True]

    def emit(kind, payload, source, **kw):
        seen.append((kind, sanitize_payload(payload, privacy)))

    context = browser.new_context()
    Instrumentation(context, emit, SessionClock(), privacy, lambda: active[0])
    page = context.new_page()
    load_fixture(page, web_page["html"])
    before = len(seen)
    active[0] = False
    page.locator("#button").click()
    page.wait_for_timeout(100)
    assert len(seen) == before
    active[0] = True
    page.locator("#button").click()
    page.wait_for_timeout(100)
    assert len(seen) > before
    context.close()


def test_real_managed_browser_persists_through_controller(settings, web_page):
    settings.browser = BrowserConfig(enabled=True, start_url="about:blank")
    opts = launch_options()
    if not opts.get("executable_path"):
        pytest.skip("This full lifecycle test requires an explicitly available Chromium executable")
    settings.browser.executable = opts.pop("executable_path")
    c = SessionController(settings)
    c.browser_factory = lambda *a, **kw: ManagedBrowser(
        *a,
        **kw,
        launch_options=opts,
        page_initializer=lambda page: load_fixture(page, web_page["auto"]),
    )
    try:
        m = c.start(
            "Synthetic managed browser integration",
            "Observe local fixture",
            consent=True,
            source=SyntheticSource(),
            synthetic=True,
        )
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline and c.browser.stats().get("actions", 0) < 2:
            time.sleep(0.05)
        m = c.stop()
    finally:
        if c.manifest and c.manifest.state.value not in {"COMPLETED", "FAILED"}:
            c.stop()
    assert m.state.value == "COMPLETED", m.failure_codes
    text = (c.repository.path(m.session_id) / "events.jsonl").read_text()
    assert "FAKE_PASSWORD_FOR_TEST" not in text
    events = list(iter_jsonl(c.repository.path(m.session_id) / "events.jsonl"))
    assert any(e["type"] == "browser_action" for e in events)
    assert all(e["session_id"] == str(m.session_id) for e in events)


def test_actual_local_http_navigation(browser, web_page):
    from playwright.sync_api import Error

    if not web_page["url"]:
        pytest.skip("Local HTTP socket binding is not permitted in this environment")
    privacy = PrivacyConfig(url_detail="path")
    seen = []

    def emit(kind, payload, source, **kw):
        seen.append((kind, sanitize_payload(payload, privacy)))

    context = browser.new_context()
    Instrumentation(context, emit, SessionClock(), privacy)
    try:
        page = context.new_page()
        try:
            page.goto(web_page["url"] + "/index.html?token=URL_SECRET#FRAGMENT_SECRET")
        except Error as exc:
            if "ERR_BLOCKED_BY_ADMINISTRATOR" in str(exc):
                pytest.skip(
                    "Chromium administrator policy blocks local HTTP; navigation NOT VERIFIED, no policy bypass attempted"
                )
            raise
        page.locator("#next").click()
        page.wait_for_load_state()
        assert any(
            kind == "browser_navigation" and p.action == "start" and p.url.endswith("/second.html")
            for kind, p in seen
        )
        encoded = json.dumps([(k, p.model_dump(mode="json")) for k, p in seen])
        assert "URL_SECRET" not in encoded and "FRAGMENT_SECRET" not in encoded
    finally:
        context.close()


def test_page_script_claim_of_trusted_click_is_not_verified(browser, web_page):
    privacy = PrivacyConfig()
    seen = []
    context = browser.new_context()
    ins = Instrumentation(
        context,
        lambda kind, payload, source, **kw: seen.append((kind, payload)),
        SessionClock(),
        privacy,
    )
    page = context.new_page()
    load_fixture(page, web_page["html"])
    page.evaluate(
        "window.__idra_event({action:'click',tag:'button',redacted:true,is_trusted:true,outcome:'navigation_completed'})"
    )
    page.wait_for_timeout(100)
    actions = [p for kind, p in seen if kind == "browser_action"]
    assert actions and all(
        p.is_trusted is None and p.outcome == "observed_event_only" for p in actions
    )
    assert ins.counts["actions"] >= 1
    context.close()
