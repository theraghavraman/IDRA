(() => {
  if (window.__idraInstalled) return;
  window.__idraInstalled = true;
  const settings = __IDRA_OPTIONS__;
  const implicitRoles = {BUTTON:'button', A:'link', SELECT:'combobox', TEXTAREA:'textbox', INPUT:'textbox'};
  const metadata = target => {
    const element = target instanceof Element ? target : null;
    if (!element) return {};
    const formInput = ['INPUT','TEXTAREA','SELECT'].includes(element.tagName) || element.isContentEditable;
    const type = element.getAttribute('type') || '';
    const sensitive = formInput || /pass|secret|token|auth|credit|ssn|otp/i.test(
      (element.getAttribute('autocomplete') || '') + ' ' + (element.getAttribute('name') || ''));
    let label = null;
    if (settings.labels && !sensitive) {
      label = element.getAttribute('aria-label') || (element.labels && element.labels[0] && element.labels[0].textContent) || '';
      if (!label && ['BUTTON','A'].includes(element.tagName)) label = element.textContent || '';
      label = label.trim().slice(0, 256);
    }
    return {tag:element.tagName.toLowerCase(), role:(element.getAttribute('role') || implicitRoles[element.tagName] || '').slice(0,64),
            input_type:type.slice(0,32), sensitive:sensitive, label:label};
  };
  const send = (action, event, extra={}) => {
    const data = {action, ...metadata(event.target), ...extra, redacted:true,
      viewport_width:innerWidth, viewport_height:innerHeight,
      browser_timestamp_ms:performance.now(), browser_time_origin_ms:performance.timeOrigin,
      is_trusted:event.isTrusted, outcome:'observed_event_only'};
    // Never serialize .value, keystrokes, DOM snapshots, clipboard, IDs or cookies.
    if (typeof window.__idra_event === 'function') window.__idra_event(data).catch(() => {});
  };
  document.addEventListener('click', e => send('click', e, {x:e.clientX, y:e.clientY, coordinate_space:'viewport'}), true);
  document.addEventListener('input', e => send('input', e), true);
  document.addEventListener('change', e => send('change', e), true);
  document.addEventListener('focusin', e => send('focus', e), true);
  let lastScroll = 0;
  let lastX = scrollX, lastY = scrollY;
  document.addEventListener('scroll', e => {
    const now = performance.now();
    if (now - lastScroll < 100) return;
    send('scroll', e, {dx:scrollX-lastX, dy:scrollY-lastY});
    lastX = scrollX; lastY = scrollY; lastScroll = now;
  }, true);
})();
