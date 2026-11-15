"""Instrumentation applies only to this app's explicitly launched browser context."""
from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict
from pathlib import Path

from idra.events.models import Payload


class Instrumentation:
    def __init__(self, context, emit, clock, privacy, is_active=lambda: True):
        self.context, self.emit, self.clock, self.privacy = context, emit, clock, privacy
        self.is_active = is_active
        self.counts = {"actions": 0, "navigations": 0, "rejected": 0, "rate_limited": 0, "uncalibrated": 0}
        self.calibrations = OrderedDict()
        self.titles = {}
        self.window_start = time.monotonic()
        self.window_count = 0
        context.expose_binding("__idra_event", self._binding)
        script = Path(__file__).with_name("instrumentation.js").read_text(encoding="utf-8")
        script = script.replace("__IDRA_OPTIONS__", json.dumps({"labels": privacy.browser_labels}))
        context.add_init_script(script=script)
        context.on("page", self._page)
        for page in context.pages:
            self._page(page)
    def _binding(self, source, data):
        received = self.clock.now_ns()
        if not self.is_active():
            return
        now = time.monotonic()
        if now - self.window_start >= 1:
            self.window_start, self.window_count = now, 0
        self.window_count += 1
        if self.window_count > 250:
            self.counts["rate_limited"] += 1
            return
        try:
            allowed = {"action", "x", "y", "coordinate_space", "dx", "dy", "tag", "role", "label",
                       "input_type", "sensitive", "redacted", "viewport_width", "viewport_height",
                       "browser_timestamp_ms", "browser_time_origin_ms", "is_trusted", "outcome"}
            if not isinstance(data, dict) or not set(data).issubset(allowed):
                raise ValueError("Unexpected browser payload")
            payload = Payload.model_validate(data)
            tags = {"a", "button", "input", "textarea", "select", "option", "label", "div", "span", "body", "html", "form", "p", "img", "svg", "path", "canvas", "li", "ul", "ol", "td", "th", "tr", "table"}
            roles = {"button", "link", "textbox", "combobox", "checkbox", "radio", "menuitem", "tab", "dialog", "listbox", "option", "slider", "switch", "spinbutton", "searchbox", "gridcell", "row", "cell", "heading", "navigation", "main", "form"}
            input_types = {"", "text", "password", "email", "number", "tel", "url", "search", "date", "time", "datetime-local", "month", "week", "checkbox", "radio", "button", "submit", "reset", "file", "hidden", "range", "color"}
            payload.tag = payload.tag if payload.tag in tags else "other"
            payload.role = payload.role if payload.role in roles else None
            payload.input_type = payload.input_type if payload.input_type in input_types else None
            if payload.action not in {"click", "input", "change", "focus", "scroll"}:
                raise ValueError("Unexpected action")
            # Playwright bindings are callable by arbitrary page JavaScript; neither
            # is_trusted nor outcome in the submitted payload establishes provenance.
            payload.is_trusted = None
            payload.outcome = "observed_event_only"
            payload.url = source["frame"].url[:2048]
            t_ns, kind, uncertainty = received, "received", None
            if payload.browser_timestamp_ms is not None and payload.browser_time_origin_ms is not None:
                key = (id(source["frame"]), payload.browser_time_origin_ms)
                if key in self.calibrations:
                    offset, bound = self.calibrations[key]
                    estimate = offset + round(payload.browser_timestamp_ms * 1e6)
                    if 0 <= estimate <= received + bound:
                        t_ns, kind, uncertainty = estimate, "calibrated", bound
            if kind == "received":
                self.counts["uncalibrated"] += 1
            self.emit("browser_action", payload, "browser", t_ns=t_ns,
                      received_t_ns=received, timestamp_kind=kind, uncertainty_ns=uncertainty)
            self.counts["actions"] += 1
        except Exception:
            # Page scripts are untrusted. Do not log their supplied contents.
            self.counts["rejected"] += 1
    def calibrate(self, frame):
        """Call from the owner event loop, never from an exposed binding callback.

        Re-entering synchronous Playwright evaluate inside a JS binding can deadlock
        the page action waiting for that binding. Uncalibrated events retain their
        actual host receive time until this explicit calibration succeeds.
        """
        try:
            before = self.clock.now_ns()
            value = frame.evaluate("({now:performance.now(), origin:performance.timeOrigin})")
            after = self.clock.now_ns()
            key = (id(frame), value["origin"])
            self.calibrations[key] = ((before + after) // 2 - round(value["now"] * 1e6), (after - before) // 2)
            while len(self.calibrations) > 128:
                self.calibrations.popitem(last=False)
            if self.privacy.browser_titles and frame == frame.page.main_frame:
                self.titles[id(frame.page)] = frame.page.title()[:256]
            return True
        except Exception:
            return False
    def calibrate_pages(self):
        for page in self.context.pages[:16]:
            if not page.is_closed():
                for frame in page.frames[:16]:
                    self.calibrate(frame)

    def _navigation(self, page, action, reason=None, url=None):
        if not self.is_active():
            return
        try:
            title = self.titles.get(id(page)) if self.privacy.browser_titles and action == "complete" else None
            outcome = {"complete":"navigation_completed", "failed":"navigation_failed"}.get(action, "observed_event_only")
            self.emit("browser_navigation", Payload(action=action, url=(url or page.url)[:2048], title=title,
                      reason=reason, outcome=outcome), "browser", timestamp_kind="received")
            self.counts["navigations"] += 1
        except Exception:
            self.counts["rejected"] += 1
    def _page(self, page):
        page.on("request", lambda req: self._navigation(page, "start", "NAVIGATION_REQUESTED", req.url)
                if req.is_navigation_request() and req.frame == page.main_frame else None)
        page.on("load", lambda: self._navigation(page, "complete", "LOAD_EVENT_OBSERVED"))
        page.on("requestfailed", lambda req: self._navigation(page, "failed", "NAVIGATION_REQUEST_FAILED")
                if req.is_navigation_request() else None)

class ManagedBrowser:
    def __init__(self, config, privacy, clock, emit, is_active, *, launch_options=None, page_initializer=None):
        self.config, self.privacy, self.clock = config, privacy, clock
        self.emit, self.is_active = emit, is_active
        # Dependency-injection hook for controlled headless integration tests; not a GUI setting.
        self.launch_options = launch_options or {}
        self.page_initializer = page_initializer
        self.stopping = threading.Event()
        self.ready = threading.Event()
        self.status = "not_started"
        self.error = None
        self.instrumentation = None
        self.thread = threading.Thread(target=self._run, name="idra-browser", daemon=True)
    def start(self):
        self.thread.start()
        if not self.ready.wait(25):
            self.stopping.set()
            raise RuntimeError("BROWSER_START_TIMEOUT")
        if self.error:
            raise RuntimeError(self.error)
    def _run(self):
        self.status = "starting"
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                opts = {"headless": False, **self.launch_options}
                if self.config.executable:
                    opts["executable_path"] = self.config.executable
                browser = pw.chromium.launch(**opts)
                try:
                    context = browser.new_context(no_viewport=True, accept_downloads=False)
                    context.set_default_timeout(5000)
                    self.instrumentation = Instrumentation(context, self.emit, self.clock, self.privacy, self.is_active)
                    page = context.new_page()
                    page.goto(self.config.start_url, wait_until="domcontentloaded", timeout=15000)
                    if self.page_initializer is not None:
                        self.page_initializer(page)
                    self.instrumentation.calibrate_pages()
                    self.status = "instrumented"
                    self.ready.set()
                    last_calibration = time.monotonic()
                    while not self.stopping.is_set() and browser.is_connected():
                        pages = [p for p in context.pages if not p.is_closed()]
                        if not pages:
                            self.status = "disconnected"
                            break
                        pages[0].wait_for_timeout(100)
                        if time.monotonic() - last_calibration >= 1:
                            self.instrumentation.calibrate_pages()
                            last_calibration = time.monotonic()
                    context.close()
                finally:
                    browser.close()
        except Exception as exc:
            self.error = f"BROWSER_UNAVAILABLE:{type(exc).__name__}"
            self.status = "failed"
        finally:
            if self.status == "instrumented":
                self.status = "closed"
            self.ready.set()
    def stats(self):
        return dict(self.instrumentation.counts) if self.instrumentation else {}
    def stop(self):
        self.stopping.set()
        self.thread.join(30)
        if self.thread.is_alive():
            raise RuntimeError("BROWSER_SHUTDOWN_TIMEOUT")
