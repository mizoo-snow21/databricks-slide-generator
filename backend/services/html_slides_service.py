"""Self-contained HTML slide deck from LLM create-from-spec JSON."""

from __future__ import annotations

import base64
import html
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

WIDGET_REF_KEYS = frozenset({"_widget_id", "_left_widget_id", "_right_widget_id"})


def _safe_chart_dom_id(widget_id: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(widget_id)).strip("-")
    return s or "w"


def _chart_element_id(widget_id: str, slide_index: int) -> str:
    return f"chart-{_safe_chart_dom_id(widget_id)}-{slide_index}"


def _vega_mount_script(specs_by_element_id: dict[str, dict[str, Any]]) -> str:
    if not specs_by_element_id:
        return ""
    payload = json.dumps(specs_by_element_id, ensure_ascii=False)
    payload = payload.replace("</", "<\\/")
    return f"""
  <script>
  (function () {{
    var specs = {payload};
    function mountAll() {{
      if (typeof vegaEmbed === 'undefined') return;
      Object.keys(specs).forEach(function (id) {{
        var el = document.getElementById(id);
        if (!el) return;
        vegaEmbed(el, specs[id], {{actions: false, renderer: 'svg', theme: 'default'}}).catch(function (e) {{ console.warn(e); }});
      }});
    }}
    if (document.readyState === 'loading') {{
      document.addEventListener('DOMContentLoaded', mountAll);
    }} else {{
      mountAll();
    }}
  }})();
  </script>
"""


def _esc(s: Any) -> str:
    if s is None:
        return ""
    return html.escape(str(s), quote=True)


def _optional_p(class_name: str, text: Any) -> str:
    if not text:
        return ""
    return "".join(('<p class="', class_name, '">', _esc(text), "</p>"))


def _optional_h2(class_name: str, text: Any) -> str:
    if not text:
        return ""
    return "".join(('<h2 class="', class_name, '">', _esc(text), "</h2>"))


def _default_brand() -> Dict[str, str]:
    return {
        "primary": "#333333",
        "secondary": "#666666",
        "accent": "#0066CC",
        "text_dark": "#202124",
        "text_light": "#FFFFFF",
        "font": "Noto Sans JP",
    }


def _merge_brand(brand: Optional[Dict[str, Any]]) -> Dict[str, str]:
    b = _default_brand()
    if brand:
        for k in b:
            if k in brand and brand[k]:
                b[k] = str(brand[k])
    return b


def _normalize_layout(layout: str) -> str:
    lo = (layout or "content_basic").strip()
    if lo.startswith("section_break"):
        return "section_break"
    return lo


def _bullets_html(bullets: Any) -> str:
    if not bullets:
        return ""
    if isinstance(bullets, str):
        parts = [p.strip() for p in re.split(r"[\n;]", bullets) if p.strip()]
    elif isinstance(bullets, list):
        parts = [str(b).strip() for b in bullets if str(b).strip()]
    else:
        return ""
    if not parts:
        return ""
    items = "".join(f"<li>{_esc(p)}</li>" for p in parts)
    return f"<ul class='slide-bullets'>{items}</ul>"


def _table_html(table: Any, *, dark: bool) -> str:
    if not isinstance(table, dict):
        return ""
    data = table.get("data")
    if not data or not isinstance(data, list):
        return ""
    rows_html: list[str] = []
    for ri, row in enumerate(data):
        if not isinstance(row, (list, tuple)):
            continue
        if ri == 0:
            cells = "".join(f"<th>{_esc(c)}</th>" for c in row)
            rows_html.append(f"<tr>{cells}</tr>")
        else:
            cells = "".join(f"<td>{_esc(c)}</td>" for c in row)
            rows_html.append(f"<tr>{cells}</tr>")
    if not rows_html:
        return ""
    cls = "slide-table slide-table-dark" if dark else "slide-table"
    return f"<div class='table-wrap'><table class='{cls}'>{''.join(rows_html)}</table></div>"


def _widget_block(
    slide: Dict[str, Any],
    images: Optional[Dict[str, str]],
    widget_charts: Optional[Dict[str, Dict[str, Any]]],
    slide_index: int,
    chart_mounts: Dict[str, Dict[str, Any]],
) -> str:
    wid = slide.get("_widget_id")
    left = slide.get("_left_widget_id")
    right = slide.get("_right_widget_id")
    chunks: list[str] = []

    def single_widget(ref: Any) -> str:
        if not ref:
            return ""
        rs = str(ref)
        spec = widget_charts.get(rs) if widget_charts and rs in widget_charts else None
        if spec:
            cid = _chart_element_id(rs, slide_index)
            chart_mounts[cid] = spec
            return (
                f"<div class='widget-single'><div class='vl-chart' "
                f"id='{cid}'></div></div>"
            )
        if images:
            src = images.get(rs)
            if src:
                return f"<div class='widget-single'><img src='{src}' alt='' /></div>"
        return ""

    if wid:
        block = single_widget(wid)
        if block:
            chunks.append(block)
    if left or right:
        row_inner: list[str] = ["<div class='widget-row'>"]
        row_has_content = False
        for ref in (left, right):
            if ref:
                cell_inner = single_widget(ref)
                if cell_inner:
                    row_has_content = True
                row_inner.append(f"<div class='widget-half'>{cell_inner}</div>")
            else:
                row_inner.append("<div class='widget-half'></div>")
        row_inner.append("</div>")
        if row_has_content:
            chunks.append("".join(row_inner))
    return "".join(chunks)


def _columns_2col(spec: Dict[str, Any]) -> tuple[str, str, str, str]:
    cols = spec.get("columns")
    if isinstance(cols, list) and len(cols) >= 2 and isinstance(cols[0], dict):

        def _col_parts(col: Any) -> tuple[str, str]:
            if not isinstance(col, dict):
                return "", str(col)
            h = str(col.get("header") or "")
            items = col.get("items") or []
            if isinstance(items, list):
                body = "\n".join(str(i) for i in items if str(i).strip())
            else:
                body = str(items) if items else ""
            ctxt = col.get("content")
            if ctxt:
                body = (body + "\n" + str(ctxt)).strip() if body else str(ctxt)
            return h, body

        h1, b1 = _col_parts(cols[0])
        h2, b2 = _col_parts(cols[1])
        return h1, b1, h2, b2
    left = spec.get("left")
    right = spec.get("right")
    if left or right:
        lh = str(spec.get("left_header") or "")
        rh = str(spec.get("right_header") or "")

        def _list_lines(v: Any) -> str:
            if isinstance(v, list):
                return "\n".join(str(x) for x in v if str(x).strip())
            return str(v) if v else ""

        return lh, _list_lines(left), rh, _list_lines(right)
    if isinstance(cols, list) and len(cols) >= 4:
        return str(cols[0]), str(cols[1]), str(cols[2]), str(cols[3])
    if isinstance(cols, list) and len(cols) == 2:
        return "", str(cols[0]), "", str(cols[1])
    return (
        str(spec.get("col1_header") or ""),
        str(spec.get("col1_body") or ""),
        str(spec.get("col2_header") or ""),
        str(spec.get("col2_body") or ""),
    )


def _slide_body_html(
    slide: Dict[str, Any],
    brand: Dict[str, str],
    images: Optional[Dict[str, str]],
    widget_charts: Optional[Dict[str, Dict[str, Any]]],
    slide_index: int,
    chart_mounts: Dict[str, Dict[str, Any]],
) -> str:
    layout = _normalize_layout(str(slide.get("layout") or ""))
    widgets = _widget_block(slide, images, widget_charts, slide_index, chart_mounts)

    if layout == "title":
        sub = slide.get("subtitle") or slide.get("body")
        sub_html = _optional_p("slide-subtitle", sub)
        return (
            f"<div class='slide-stack center'>"
            f"<h1 class='slide-title'>{_esc(slide.get('title'))}</h1>"
            f"{sub_html}"
            f"{widgets}"
            f"</div>"
        )

    if layout in ("content_basic", "content_subtitle"):
        sub = slide.get("subtitle")
        body = slide.get("body")
        sub_html = _optional_p("slide-subtitle", sub)
        body_html = _optional_p("slide-body", body)
        parts = (
            f"<h2 class='slide-heading'>{_esc(slide.get('title'))}</h2>"
            f"{sub_html}"
            f"{body_html}"
            f"{_bullets_html(slide.get('bullets'))}"
            f"{widgets}"
        )
        return f"<div class='slide-stack'>{parts}</div>"

    if layout == "content_2col":
        h1, b1, h2, b2 = _columns_2col(slide)
        col = (
            "<div class='col-grid-2'>"
            f"<div class='col'><h3>{_esc(h1)}</h3><p>{_esc(b1)}</p></div>"
            f"<div class='col'><h3>{_esc(h2)}</h3><p>{_esc(b2)}</p></div>"
            "</div>"
        )
        return (
            f"<div class='slide-stack'>"
            f"<h2 class='slide-heading'>{_esc(slide.get('title'))}</h2>"
            f"{col}{widgets}</div>"
        )

    if layout == "content_3col":
        blocks = []
        for i in (1, 2, 3):
            hh = slide.get(f"header{i}")
            bb = slide.get(f"body{i}")
            blocks.append(
                f"<div class='col'><h3>{_esc(hh)}</h3><p>{_esc(bb)}</p></div>",
            )
        return (
            f"<div class='slide-stack'>"
            f"<h2 class='slide-heading'>{_esc(slide.get('title'))}</h2>"
            f"<div class='col-grid-3'>{''.join(blocks)}</div>{widgets}</div>"
        )

    if layout == "title_only":
        tbl = _table_html(slide.get("table"), dark=False)
        return (
            f"<div class='slide-stack'>"
            f"<h2 class='slide-heading'>{_esc(slide.get('title'))}</h2>"
            f"{tbl}{widgets}</div>"
        )

    if layout == "section_break":
        return (
            f"<div class='slide-stack center section-break'>"
            f"<h1 class='section-title'>{_esc(slide.get('title'))}</h1>"
            f"{widgets}</div>"
        )

    if layout == "closing":
        sub = slide.get("subtitle")
        sub_html = f'<p class="slide-subtitle">{_esc(sub)}</p>' if sub else ""
        return (
            f"<div class='slide-stack center closing'>"
            f"<h1 class='closing-title'>{_esc(slide.get('title') or 'Thank you')}</h1>"
            f"{sub_html}{widgets}</div>"
        )

    if layout == "quote_dark":
        sub = slide.get("subtitle")
        cite_html = f'<cite class="quote-by">{_esc(sub)}</cite>' if sub else ""
        return (
            f"<div class='slide-stack center quote'>"
            f"<blockquote class='quote-text'>{_esc(slide.get('title'))}</blockquote>"
            f"{cite_html}{widgets}</div>"
        )

    if layout == "content_basic_dark":
        sub = slide.get("subtitle")
        body = slide.get("body")
        sub_html = _optional_p("slide-subtitle", sub)
        body_html = _optional_p("slide-body", body)
        parts = (
            f"<h2 class='slide-heading'>{_esc(slide.get('title'))}</h2>"
            f"{sub_html}"
            f"{body_html}"
            f"{_bullets_html(slide.get('bullets'))}"
            f"{_table_html(slide.get('table'), dark=True)}"
            f"{widgets}"
        )
        return f"<div class='slide-stack'>{parts}</div>"

    if layout == "blank":
        return f"<div class='slide-stack'>{widgets}</div>"

    # Fallback: show JSON-safe dump of common fields
    title = slide.get("title")
    body = slide.get("body")
    title_html = _optional_h2("slide-heading", title)
    body_html = _optional_p("slide-body", body)
    return (
        f"<div class='slide-stack'>"
        f"{title_html}"
        f"{body_html}"
        f"{_bullets_html(slide.get('bullets'))}"
        f"{_table_html(slide.get('table'), dark=False)}"
        f"{widgets}</div>"
    )


def _slide_class(layout: str) -> str:
    lo = _normalize_layout(layout)
    dark_layouts = frozenset(
        {
            "section_break",
            "closing",
            "quote_dark",
            "content_basic_dark",
        },
    )
    base = "slide"
    if lo in dark_layouts:
        return f"{base} slide-dark"
    return f"{base} slide-light"


def _font_href(font_name: str) -> str:
    fam = re.sub(r"\s+", "+", font_name.strip())
    return (
        f"https://fonts.googleapis.com/css2?family={fam}:wght@400;600;700&display=swap"
    )


def generate_html_slides(
    title: str,
    slides: List[Dict[str, Any]],
    brand: Optional[Dict[str, Any]] = None,
    widget_images: Optional[Dict[str, str]] = None,
    widget_charts: Optional[Dict[str, Dict[str, Any]]] = None,
) -> str:
    """Build a single HTML document with scroll-snap slides from create-from-spec dicts."""
    b = _merge_brand(brand)
    font_url = _font_href(b["font"])
    sections: list[str] = []
    dots: list[str] = []
    chart_mounts: dict[str, dict[str, Any]] = {}

    for i, slide in enumerate(slides):
        layout_raw = str(slide.get("layout") or "")
        cls = _slide_class(layout_raw)
        inner = _slide_body_html(
            slide, b, widget_images, widget_charts, i, chart_mounts
        )
        sections.append(f"<section class='{cls}' data-index='{i}'>{inner}</section>")
        dots.append(
            f"<button type='button' class='dot' data-index='{i}' aria-label='Slide {i + 1}'></button>"
        )

    slides_html = "\n".join(sections)
    dots_html = "".join(dots)

    doc_title = _esc(title)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{doc_title}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="{font_url}" rel="stylesheet" />
  <script src="https://cdn.jsdelivr.net/npm/vega@5"></script>
  <script src="https://cdn.jsdelivr.net/npm/vega-lite@5"></script>
  <script src="https://cdn.jsdelivr.net/npm/vega-embed@6"></script>
  <style>
:root {{
  --primary: {b["primary"]};
  --secondary: {b["secondary"]};
  --accent: {b["accent"]};
  --text-dark: {b["text_dark"]};
  --text-light: {b["text_light"]};
  --font: "{b["font"]}", system-ui, sans-serif;
}}
* {{ box-sizing: border-box; }}
html, body {{
  margin: 0;
  padding: 0;
  height: 100%;
  font-family: var(--font);
  scroll-behavior: smooth;
}}
#deck {{
  height: 100vh;
  overflow-y: auto;
  overflow-x: hidden;
  scroll-snap-type: y mandatory;
  scroll-padding-top: 0;
}}
.slide {{
  min-height: 100vh;
  height: auto;
  scroll-snap-align: start;
  scroll-snap-stop: always;
  padding: 3rem 4.5rem 3rem 3rem;
  display: flex;
  align-items: center;
  justify-content: center;
}}
.slide-light {{
  background: #f8fafc;
  color: var(--text-dark);
}}
.slide-dark {{
  background: linear-gradient(145deg, var(--primary) 0%, #1e1e2e 100%);
  color: var(--text-light);
}}
.slide-inner {{ width: 100%; max-width: 72rem; }}
.slide-stack {{ width: 100%; }}
.slide-stack.center {{ text-align: center; }}
.slide-title {{
  font-size: clamp(2rem, 4vw, 3.25rem);
  font-weight: 700;
  margin: 0 0 0.75rem;
  color: inherit;
}}
.slide-heading {{
  font-size: clamp(1.5rem, 3vw, 2.25rem);
  font-weight: 700;
  margin: 0 0 1rem;
  color: inherit;
  border-bottom: 3px solid var(--accent);
  padding-bottom: 0.35rem;
  display: inline-block;
}}
.slide-subtitle {{
  font-size: 1.2rem;
  color: var(--secondary);
  margin: 0 0 1rem;
}}
.slide-dark .slide-subtitle {{ color: rgba(255,255,255,0.85); }}
.slide-body {{ font-size: 1.05rem; line-height: 1.55; margin: 0 0 1rem; max-width: 55rem; }}
.slide-stack.center .slide-body {{ margin-left: auto; margin-right: auto; }}
.slide-bullets {{ margin: 0.5rem 0 0; padding-left: 1.25rem; font-size: 1.05rem; line-height: 1.5; }}
.slide-bullets li {{ margin-bottom: 0.35rem; }}
.col-grid-2, .col-grid-3 {{
  display: grid;
  gap: 1.5rem;
  margin-top: 1rem;
}}
.col-grid-2 {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
.col-grid-3 {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
.col h3 {{
  margin: 0 0 0.5rem;
  font-size: 1.1rem;
  color: var(--accent);
}}
.slide-dark .col h3 {{ color: var(--accent); }}
.col p {{ margin: 0; font-size: 0.98rem; line-height: 1.45; }}
.table-wrap {{ overflow: auto; margin-top: 1rem; max-width: 100%; }}
.slide-table {{ width: 100%; border-collapse: collapse; font-size: 0.92rem; }}
.slide-table th {{
  background: var(--accent);
  color: var(--text-light);
  text-align: left;
  padding: 0.5rem 0.65rem;
}}
.slide-table-dark th {{ background: var(--accent); color: var(--text-light); }}
.slide-table td {{ border: 1px solid #cbd5e1; padding: 0.45rem 0.6rem; }}
.slide-table-dark td {{ border-color: rgba(255,255,255,0.25); }}
.slide-dark .slide-table td {{ color: var(--text-light); }}
.section-break .section-title {{
  font-size: clamp(2.2rem, 5vw, 3.5rem);
  font-weight: 700;
  margin: 0;
  color: var(--text-light);
}}
.closing .closing-title {{ font-size: clamp(2rem, 4vw, 3rem); margin: 0; }}
.quote-text {{
  font-size: clamp(1.4rem, 3vw, 2rem);
  font-weight: 600;
  font-style: italic;
  margin: 0 0 1rem;
  line-height: 1.4;
  border: none;
}}
.quote-by {{ font-size: 1rem; opacity: 0.9; font-style: normal; }}
.widget-single img, .widget-half img {{
  display: block;
  max-width: 100%;
  height: auto;
  margin-top: 1rem;
  border-radius: 8px;
  box-shadow: 0 4px 24px rgba(0,0,0,0.12);
}}
.widget-row {{
  display: flex;
  gap: 1rem;
  margin-top: 1rem;
  flex-wrap: wrap;
  justify-content: center;
}}
.widget-half {{ flex: 1 1 45%; min-width: 200px; }}
.widget-half img {{ width: 100%; }}
.vl-chart {{
  width: 100%;
  max-width: 640px;
  min-height: 260px;
  margin-top: 1rem;
}}
.widget-half .vl-chart {{ max-width: 100%; }}
.nav-dots {{
  position: fixed;
  right: 14px;
  top: 50%;
  transform: translateY(-50%);
  z-index: 50;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 8px;
  background: rgba(255,255,255,0.35);
  border-radius: 999px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.08);
}}
.nav-dots .dot {{
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: none;
  padding: 0;
  background: rgba(0,0,0,0.25);
  cursor: pointer;
}}
.nav-dots .dot.active {{ background: var(--accent); transform: scale(1.15); }}
.toolbar {{
  position: fixed;
  top: 12px;
  left: 12px;
  z-index: 50;
  display: flex;
  gap: 8px;
}}
.toolbar button {{
  font-family: var(--font);
  font-size: 0.85rem;
  font-weight: 600;
  padding: 0.4rem 0.75rem;
  border-radius: 8px;
  border: 1px solid rgba(0,0,0,0.12);
  background: rgba(255,255,255,0.9);
  cursor: pointer;
}}
.toolbar button:hover {{ background: #fff; }}
@media (max-width: 720px) {{
  .col-grid-2, .col-grid-3 {{ grid-template-columns: 1fr; }}
  .slide {{ padding: 2.5rem 3rem 2rem 1.25rem; }}
}}
  </style>
</head>
<body>
  <div id="deck" tabindex="0">
    <div class="toolbar">
      <button type="button" id="fs-btn" title="Fullscreen">Fullscreen</button>
    </div>
    <nav class="nav-dots" aria-label="Slides">
      {dots_html}
    </nav>
    {slides_html}
  </div>
  <script>
(function () {{
  const deck = document.getElementById('deck');
  const slides = Array.from(document.querySelectorAll('.slide'));
  const dots = Array.from(document.querySelectorAll('.dot'));
  let idx = 0;

  function updateDots() {{
    dots.forEach((d, i) => d.classList.toggle('active', i === idx));
  }}

  function go(i) {{
    if (!slides.length) return;
    idx = Math.max(0, Math.min(slides.length - 1, i));
    slides[idx].scrollIntoView({{ behavior: 'smooth', block: 'start' }});
    updateDots();
  }}

  dots.forEach((d) => {{
    d.addEventListener('click', () => go(parseInt(d.getAttribute('data-index'), 10)));
  }});

  document.addEventListener('keydown', (e) => {{
    const tag = (e.target && e.target.tagName) || '';
    if (tag === 'INPUT' || tag === 'TEXTAREA') return;
    if (['ArrowDown', 'PageDown', ' '].includes(e.key)) {{
      e.preventDefault();
      go(idx + 1);
    }} else if (['ArrowUp', 'PageUp'].includes(e.key)) {{
      e.preventDefault();
      go(idx - 1);
    }} else if (e.key === 'Home') {{
      e.preventDefault();
      go(0);
    }} else if (e.key === 'End') {{
      e.preventDefault();
      go(slides.length - 1);
    }}
  }});

  deck.addEventListener('wheel', (e) => {{
    if (Math.abs(e.deltaY) < 40) return;
    e.preventDefault();
    go(idx + (e.deltaY > 0 ? 1 : -1));
  }}, {{ passive: false }});

  const obs = new IntersectionObserver(
    (entries) => {{
      entries.forEach((en) => {{
        if (!en.isIntersecting) return;
        const i = slides.indexOf(en.target);
        if (i >= 0) {{
          idx = i;
          updateDots();
        }}
      }});
    }},
    {{ root: deck, threshold: 0.55 }},
  );
  slides.forEach((s) => obs.observe(s));

  document.getElementById('fs-btn').addEventListener('click', () => {{
    if (!document.fullscreenElement) deck.requestFullscreen().catch(() => {{}});
    else document.exitFullscreen();
  }});

  deck.focus({{ preventScroll: true }});
  updateDots();
}})();
  </script>
{_vega_mount_script(chart_mounts)}
</body>
</html>
"""


def widget_image_data_uri(png_path: str) -> str:
    """Load a PNG file and return a data URI suitable for img src."""
    raw = Path(png_path).read_bytes()
    b64 = base64.standard_b64encode(raw).decode("ascii")
    return f"data:image/png;base64,{b64}"
