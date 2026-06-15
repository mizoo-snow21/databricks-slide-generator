"""Trusted inspector script for the deck editor iframe.

Plain JavaScript stored as a Python string. Server-side injected by
GET /api/decks/{id}/edit-html AFTER the canonical sanitized HTML.
LLM cannot influence this script.
"""

INSPECTOR_SCRIPT_SRC: str = r"""
(function () {
  // Some elements are NOT useful comment targets — selecting them would
  // either force the LLM into a no-op (widget-chart PNG: backed by real
  // data, can't be hand-edited; deck-logo: static asset) or land the
  // comment on something the user didn't visually intend. For these,
  // escalate to the parent osd-id element instead.
  function isNonEditableImg(el) {
    if (!el || el.tagName !== 'IMG' || !el.classList) return false;
    return (
      el.classList.contains('widget-chart') ||
      el.classList.contains('deck-logo')
    );
  }
  function findOsdAncestor(el) {
    while (el && el !== document.documentElement) {
      if (el.dataset && el.dataset.osdId && !isNonEditableImg(el)) return el;
      el = el.parentElement;
    }
    return null;
  }
  function rectFor(el) {
    var r = el.getBoundingClientRect();
    return { x: r.left, y: r.top, w: r.width, h: r.height };
  }
  document.addEventListener('mouseover', function (e) {
    var t = findOsdAncestor(e.target);
    if (!t) return;
    var prev = document.querySelectorAll('[data-osd-hover]');
    for (var i = 0; i < prev.length; i++) prev[i].removeAttribute('data-osd-hover');
    t.setAttribute('data-osd-hover', '');
  });
  document.addEventListener('click', function (e) {
    var t = findOsdAncestor(e.target);
    if (!t) return;
    e.preventDefault();
    e.stopPropagation();
    parent.postMessage({ type: 'osd:select', target_id: t.dataset.osdId, rect: rectFor(t) }, '*');
  });
  var style = document.createElement('style');
  style.textContent = '[data-osd-hover]{outline:2px dashed rgba(0,128,255,0.6);outline-offset:2px;cursor:pointer;}[data-osd-selected]{outline:2px solid rgba(0,128,255,0.9);outline-offset:2px;}';
  document.head.appendChild(style);
  // Listen for parent → iframe scroll commands.
  window.addEventListener('message', function (e) {
    var data = e && e.data;
    if (!data || data.type !== 'osd:goto') return;
    if (typeof data.slide_id !== 'string') return;
    var sel = '[data-slide-id="' + data.slide_id.replace(/"/g, '\\"') + '"]';
    var target = document.querySelector(sel);
    if (target && typeof target.scrollIntoView === 'function') {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
  parent.postMessage({ type: 'osd:ready' }, '*');
})();
"""


def inject_inspector(html_doc: str) -> str:
    snippet = "<script>" + INSPECTOR_SCRIPT_SRC + "</script>"
    if "</body>" in html_doc:
        return html_doc.replace("</body>", snippet + "</body>", 1)
    return html_doc + snippet
