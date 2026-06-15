"""Brand stylesheets injected into decks created from preset templates.

Editorial / minimalist refit: removes AI-tell decorations (corner triangles,
left-side vertical accent stripes, accent rules under titles, eyebrow tag
chrome on every slide). Hierarchy is driven by **typography + whitespace**,
not chrome decorations. Lava is reserved as a *type* color (one accent
phrase per slide, hero numerals) — never as a strip / bar / triangle.
"""

from __future__ import annotations

DATABRICKS_CORP_BRAND_CSS = """
/* ============================================================
   Databricks Corporate brand stylesheet — editorial refit.
   Typography + whitespace drive hierarchy. NO decorative
   triangles, accent stripes, accent rules, or chrome bars.
   ============================================================ */

section.slide {
  font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, system-ui, sans-serif !important;
  position: relative !important;
  overflow: hidden !important;
  box-sizing: border-box !important;
}

/* Light slide canvas (default): warm cream bg, generous padding */
section.slide:not([data-layout="title"]):not([data-layout="section"]):not([data-layout="closing"]):not([data-layout="callout"]):not([data-layout="quote"]) {
  background: #f5f3f0 !important;
  color: #1b3139 !important;
  padding: 120px 140px 110px 140px !important;
}

/* Subtle copyright line — bottom-right, low contrast */
section.slide:not([data-layout="title"]):not([data-layout="section"]):not([data-layout="closing"]):not([data-layout="callout"]):not([data-layout="quote"])::after {
  content: "Databricks" !important;
  position: absolute !important;
  bottom: 36px !important;
  right: 140px !important;
  font-family: 'DM Sans', sans-serif !important;
  font-size: 14px !important;
  font-weight: 600 !important;
  letter-spacing: 0.18em !important;
  text-transform: uppercase !important;
  color: #1b3139 !important;
  opacity: 0.32 !important;
  z-index: 5 !important;
}

/* Dark canvas slides: cover, section divider, callout, quote, closing */
section.slide[data-layout="title"],
section.slide[data-layout="section"],
section.slide[data-layout="closing"],
section.slide[data-layout="callout"],
section.slide[data-layout="quote"] {
  background: #1b3139 !important;
  color: #f5f3f0 !important;
  padding: 140px !important;
}

/* Accent text: Lava is a TYPE color */
section.slide .accent {
  color: #ff3621 !important;
}

/* Brand chrome — limited to signature anchor slides only.
   Title cover gets a top-right Lava triangle, closing gets a
   bottom-left Lava triangle (asymmetric mirror). Section dividers
   get a short Lava rule under h2. NEVER add these to content slides. */
section.slide[data-layout="title"]::before {
  content: "" !important;
  position: absolute !important;
  top: 0 !important;
  right: 0 !important;
  width: 0 !important;
  height: 0 !important;
  border-style: solid !important;
  border-width: 0 160px 160px 0 !important;
  border-color: transparent #ff3621 transparent transparent !important;
  pointer-events: none !important;
  z-index: 0 !important;
}

section.slide[data-layout="closing"]::before {
  content: "" !important;
  position: absolute !important;
  bottom: 0 !important;
  left: 0 !important;
  width: 0 !important;
  height: 0 !important;
  border-style: solid !important;
  border-width: 160px 0 0 160px !important;
  border-color: transparent transparent transparent #ff3621 !important;
  pointer-events: none !important;
  z-index: 0 !important;
}

section.slide[data-layout="section"] h2::after {
  content: "" !important;
  display: block !important;
  width: 96px !important;
  height: 3px !important;
  background: #ff3621 !important;
  margin-top: 32px !important;
  pointer-events: none !important;
  z-index: 0 !important;
}

/* Strip any LLM-emitted decorative chrome on non-anchor slides
   (vertical/horizontal accent bars, top bars, accent rules under
   titles on content slides). The brand chrome above is delivered
   via pseudo-elements scoped to title/closing/section only — class
   names below are still off-limits everywhere. */
section.slide [class*="accent-bar"],
section.slide [class*="accent-line"],
section.slide [class*="accent-rule"],
section.slide [class*="accent-stripe"],
section.slide [class*="accent-triangle"],
section.slide [class*="cover-triangle"],
section.slide [class*="section-bar"],
section.slide [class*="section-stripe"],
section.slide [class*="closing-triangle"],
section.slide [class*="closing-bar"],
section.slide [class*="title-rule"],
section.slide [class*="title-underline"],
section.slide [class*="topbar"],
section.slide [class*="top-bar"],
section.slide hr {
  display: none !important;
}

/* Editorial typography */
section.slide h1, section.slide h2, section.slide h3 {
  font-family: 'DM Sans', sans-serif !important;
  font-weight: 700 !important;
  letter-spacing: -0.015em !important;
  margin-top: 0 !important;
}

section.slide h1 {
  font-size: 104px !important;
  line-height: 1.02 !important;
  margin-bottom: 28px !important;
}

section.slide h2 {
  font-size: 64px !important;
  line-height: 1.05 !important;
  margin-bottom: 40px !important;
}

section.slide h3 {
  font-size: 26px !important;
  line-height: 1.25 !important;
  font-weight: 600 !important;
  margin-bottom: 12px !important;
}

section.slide p, section.slide li {
  font-size: 22px !important;
  line-height: 1.5 !important;
}

/* Eyebrow / kicker text — kept tasteful: small, low-contrast,
   tracked uppercase. Drop the "tag" cliché styling. */
section.slide .eyebrow,
section.slide [class*="eyebrow"],
section.slide [class*="kicker"] {
  font-size: 14px !important;
  font-weight: 600 !important;
  letter-spacing: 0.18em !important;
  text-transform: uppercase !important;
  color: #6b7280 !important;
  background: transparent !important;
  border: 0 !important;
  padding: 0 !important;
  margin-bottom: 24px !important;
  display: block !important;
}
"""


# Dark-mode preset variant: every slide on Oat Black canvas
DATABRICKS_CORP_DARK_BRAND_CSS = """
section.slide {
  font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, system-ui, sans-serif !important;
  background: #1b3139 !important;
  color: #f5f3f0 !important;
  padding: 140px !important;
  position: relative !important;
  overflow: hidden !important;
  box-sizing: border-box !important;
}

section.slide .accent {
  color: #ff3621 !important;
}

/* Brand chrome — anchor slides only (mirrors the light variant) */
section.slide[data-layout="title"]::before {
  content: "" !important;
  position: absolute !important;
  top: 0 !important;
  right: 0 !important;
  width: 0 !important;
  height: 0 !important;
  border-style: solid !important;
  border-width: 0 160px 160px 0 !important;
  border-color: transparent #ff3621 transparent transparent !important;
  pointer-events: none !important;
  z-index: 0 !important;
}

section.slide[data-layout="closing"]::before {
  content: "" !important;
  position: absolute !important;
  bottom: 0 !important;
  left: 0 !important;
  width: 0 !important;
  height: 0 !important;
  border-style: solid !important;
  border-width: 160px 0 0 160px !important;
  border-color: transparent transparent transparent #ff3621 !important;
  pointer-events: none !important;
  z-index: 0 !important;
}

section.slide[data-layout="section"] h2::after {
  content: "" !important;
  display: block !important;
  width: 96px !important;
  height: 3px !important;
  background: #ff3621 !important;
  margin-top: 32px !important;
  pointer-events: none !important;
  z-index: 0 !important;
}

/* Same anti-tell decoration sweep as the light variant */
section.slide [class*="accent-bar"],
section.slide [class*="accent-line"],
section.slide [class*="accent-rule"],
section.slide [class*="accent-stripe"],
section.slide [class*="accent-triangle"],
section.slide [class*="cover-triangle"],
section.slide [class*="section-bar"],
section.slide [class*="section-stripe"],
section.slide [class*="closing-triangle"],
section.slide [class*="closing-bar"],
section.slide [class*="title-rule"],
section.slide [class*="title-underline"],
section.slide [class*="topbar"],
section.slide [class*="top-bar"],
section.slide hr {
  display: none !important;
}

section.slide h1, section.slide h2, section.slide h3 {
  font-family: 'DM Sans', sans-serif !important;
  font-weight: 700 !important;
  letter-spacing: -0.015em !important;
  margin-top: 0 !important;
}

section.slide h1 { font-size: 104px !important; line-height: 1.02 !important; margin-bottom: 28px !important; }
section.slide h2 { font-size: 64px !important; line-height: 1.05 !important; margin-bottom: 40px !important; }
section.slide h3 { font-size: 26px !important; line-height: 1.25 !important; font-weight: 600 !important; margin-bottom: 12px !important; }
section.slide p, section.slide li { font-size: 22px !important; line-height: 1.5 !important; }

section.slide .eyebrow,
section.slide [class*="eyebrow"],
section.slide [class*="kicker"] {
  font-size: 14px !important;
  font-weight: 600 !important;
  letter-spacing: 0.18em !important;
  text-transform: uppercase !important;
  color: #94a3b8 !important;
  background: transparent !important;
  border: 0 !important;
  padding: 0 !important;
  margin-bottom: 24px !important;
  display: block !important;
}

section.slide:not([data-layout="title"]):not([data-layout="section"]):not([data-layout="closing"]):not([data-layout="callout"]):not([data-layout="quote"])::after {
  content: "Databricks" !important;
  position: absolute !important;
  bottom: 36px !important;
  right: 140px !important;
  font-family: 'DM Sans', sans-serif !important;
  font-size: 14px !important;
  font-weight: 600 !important;
  letter-spacing: 0.18em !important;
  text-transform: uppercase !important;
  color: #f5f3f0 !important;
  opacity: 0.30 !important;
  z-index: 5 !important;
}
"""


DATABRICKS_BRAND_BRAND_CSS = """
/* Databricks Brand — white canvas + lava (palette: bg #fff, text #1b3139, accent #ff3621, muted #6f7989) */

section.slide {
  font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, system-ui, sans-serif !important;
  position: relative !important;
  overflow: hidden !important;
  box-sizing: border-box !important;
}

section.slide:not([data-layout="title"]):not([data-layout="section"]):not([data-layout="closing"]):not([data-layout="callout"]):not([data-layout="quote"]) {
  background: #ffffff !important;
  color: #1b3139 !important;
  padding: 120px !important;
}

section.slide[data-layout="title"],
section.slide[data-layout="section"],
section.slide[data-layout="closing"],
section.slide[data-layout="callout"],
section.slide[data-layout="quote"] {
  background: #ffffff !important;
  color: #1b3139 !important;
  padding: 120px !important;
}

section.slide .accent {
  color: #ff3621 !important;
}

section.slide[data-layout="title"]::before {
  content: "" !important;
  position: absolute !important;
  top: 0 !important;
  left: 0 !important;
  width: 96px !important;
  height: 6px !important;
  background: #ff3621 !important;
  pointer-events: none !important;
  z-index: 0 !important;
}

section.slide[data-layout="section"] h2::before {
  content: "" !important;
  display: inline-block !important;
  width: 12px !important;
  height: 12px !important;
  background: #ff3621 !important;
  margin-right: 24px !important;
  vertical-align: middle !important;
  pointer-events: none !important;
  z-index: 0 !important;
}

section.slide[data-layout="closing"]::after {
  content: "" !important;
  position: absolute !important;
  bottom: 32px !important;
  right: 32px !important;
  width: 16px !important;
  height: 16px !important;
  background: #ff3621 !important;
  pointer-events: none !important;
  z-index: 0 !important;
}

section.slide [class*="accent-bar"],
section.slide [class*="accent-line"],
section.slide [class*="accent-rule"],
section.slide [class*="accent-stripe"],
section.slide [class*="accent-triangle"],
section.slide [class*="cover-triangle"],
section.slide [class*="corner-triangle"],
section.slide [class*="section-bar"],
section.slide [class*="section-stripe"],
section.slide [class*="closing-triangle"],
section.slide [class*="closing-bar"],
section.slide [class*="title-rule"],
section.slide [class*="title-underline"],
section.slide [class*="topbar"],
section.slide [class*="top-bar"],
section.slide hr {
  display: none !important;
}

section.slide h1, section.slide h2, section.slide h3 {
  font-family: 'DM Sans', sans-serif !important;
  font-weight: 700 !important;
  letter-spacing: -0.015em !important;
  margin-top: 0 !important;
}

section.slide h1 { font-size: 104px !important; line-height: 1.02 !important; margin-bottom: 28px !important; }
section.slide h2 { font-size: 64px !important; line-height: 1.05 !important; margin-bottom: 40px !important; }
section.slide h3 { font-size: 26px !important; line-height: 1.25 !important; font-weight: 600 !important; margin-bottom: 12px !important; }
section.slide p, section.slide li { font-size: 22px !important; line-height: 1.5 !important; }

section.slide .eyebrow,
section.slide [class*="eyebrow"],
section.slide [class*="kicker"] {
  font-size: 14px !important;
  font-weight: 600 !important;
  letter-spacing: 0.18em !important;
  text-transform: uppercase !important;
  color: #6f7989 !important;
  background: transparent !important;
  border: 0 !important;
  padding: 0 !important;
  margin-bottom: 24px !important;
  display: block !important;
}
"""


EDITORIAL_NOIR_BRAND_CSS = """
/* Editorial Noir — dark editorial + hot orange (bg #0a0a0a, text #f6f3ec, accent #ff4f1a, muted #8a8a8a) */

section.slide {
  font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, system-ui, sans-serif !important;
  position: relative !important;
  overflow: hidden !important;
  box-sizing: border-box !important;
  background: #0a0a0a !important;
  color: #f6f3ec !important;
  padding: 140px !important;
}

section.slide .accent {
  color: #ff4f1a !important;
}

section.slide [class*="accent-bar"],
section.slide [class*="accent-line"],
section.slide [class*="accent-rule"],
section.slide [class*="accent-stripe"],
section.slide [class*="accent-triangle"],
section.slide [class*="cover-triangle"],
section.slide [class*="corner-triangle"],
section.slide [class*="section-bar"],
section.slide [class*="section-stripe"],
section.slide [class*="closing-triangle"],
section.slide [class*="closing-bar"],
section.slide [class*="title-rule"],
section.slide [class*="title-underline"],
section.slide [class*="topbar"],
section.slide [class*="top-bar"],
section.slide hr {
  display: none !important;
}

section.slide h1, section.slide h2, section.slide h3 {
  font-family: 'DM Sans', sans-serif !important;
  font-weight: 700 !important;
  letter-spacing: -0.015em !important;
  margin-top: 0 !important;
}

section.slide h1 { font-size: 104px !important; line-height: 1.02 !important; margin-bottom: 28px !important; }
section.slide h2 { font-size: 64px !important; line-height: 1.05 !important; margin-bottom: 40px !important; }
section.slide h3 { font-size: 26px !important; line-height: 1.25 !important; font-weight: 600 !important; margin-bottom: 12px !important; }
section.slide p, section.slide li { font-size: 22px !important; line-height: 1.5 !important; }

section.slide .eyebrow,
section.slide [class*="eyebrow"],
section.slide [class*="kicker"] {
  font-size: 14px !important;
  font-weight: 600 !important;
  letter-spacing: 0.18em !important;
  text-transform: uppercase !important;
  color: #8a8a8a !important;
  background: transparent !important;
  border: 0 !important;
  padding: 0 !important;
  margin-bottom: 24px !important;
  display: block !important;
}

section.slide[data-layout="section"] .eyebrow,
section.slide[data-layout="section"] [class*="eyebrow"],
section.slide[data-layout="section"] [class*="kicker"] {
  color: #ff4f1a !important;
}
"""


MINIMAL_LIGHT_BRAND_CSS = """
/* Minimal Light — quiet typographic hierarchy (bg #fafafa, text #1a1a1a, accent #0066cc, muted #8c8c8c) */

section.slide {
  font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, system-ui, sans-serif !important;
  position: relative !important;
  overflow: hidden !important;
  box-sizing: border-box !important;
  background: #fafafa !important;
  color: #1a1a1a !important;
  padding: 140px !important;
}

section.slide .accent {
  color: #0066cc !important;
}

section.slide[data-layout="section"] h2::after {
  content: "" !important;
  display: block !important;
  width: 120px !important;
  height: 1px !important;
  background: #1a1a1a !important;
  margin-top: 32px !important;
  pointer-events: none !important;
  z-index: 0 !important;
}

section.slide [class*="accent-bar"],
section.slide [class*="accent-line"],
section.slide [class*="accent-rule"],
section.slide [class*="accent-stripe"],
section.slide [class*="accent-triangle"],
section.slide [class*="cover-triangle"],
section.slide [class*="corner-triangle"],
section.slide [class*="section-bar"],
section.slide [class*="section-stripe"],
section.slide [class*="closing-triangle"],
section.slide [class*="closing-bar"],
section.slide [class*="title-rule"],
section.slide [class*="title-underline"],
section.slide [class*="topbar"],
section.slide [class*="top-bar"],
section.slide hr {
  display: none !important;
}

section.slide h1, section.slide h2, section.slide h3 {
  font-family: 'DM Sans', sans-serif !important;
  font-weight: 700 !important;
  letter-spacing: -0.015em !important;
  margin-top: 0 !important;
}

section.slide h1 { font-size: 104px !important; line-height: 1.02 !important; margin-bottom: 28px !important; }
section.slide h2 { font-size: 64px !important; line-height: 1.05 !important; margin-bottom: 40px !important; }
section.slide h3 { font-size: 26px !important; line-height: 1.25 !important; font-weight: 600 !important; margin-bottom: 12px !important; }
section.slide p, section.slide li { font-size: 22px !important; line-height: 1.5 !important; }

section.slide .eyebrow,
section.slide [class*="eyebrow"],
section.slide [class*="kicker"] {
  font-size: 14px !important;
  font-weight: 600 !important;
  letter-spacing: 0.18em !important;
  text-transform: uppercase !important;
  color: #8c8c8c !important;
  background: transparent !important;
  border: 0 !important;
  padding: 0 !important;
  margin-bottom: 24px !important;
  display: block !important;
}
"""


TECH_GRAPHITE_BRAND_CSS = """
/* Tech Graphite — graphite + mint (bg #1a1d23, text #e8eaed, accent #00a972, muted #737a85) */

section.slide {
  font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, system-ui, sans-serif !important;
  position: relative !important;
  overflow: hidden !important;
  box-sizing: border-box !important;
  background: #1a1d23 !important;
  color: #e8eaed !important;
  padding: 140px !important;
}

section.slide .accent {
  color: #00a972 !important;
}

section.slide[data-layout="title"]::before {
  content: "// genie-slide / Q2 2025" !important;
  font-family: 'DM Mono', ui-monospace, monospace !important;
  font-size: 14px !important;
  color: #737a85 !important;
  position: absolute !important;
  top: 32px !important;
  left: 32px !important;
  pointer-events: none !important;
  z-index: 0 !important;
}

section.slide[data-layout="section"] h2::before {
  content: "" !important;
  display: inline-block !important;
  width: 12px !important;
  height: 12px !important;
  border-radius: 50% !important;
  background: #00a972 !important;
  margin-right: 24px !important;
  vertical-align: middle !important;
  pointer-events: none !important;
  z-index: 0 !important;
}

section.slide [class*="accent-bar"],
section.slide [class*="accent-line"],
section.slide [class*="accent-rule"],
section.slide [class*="accent-stripe"],
section.slide [class*="accent-triangle"],
section.slide [class*="cover-triangle"],
section.slide [class*="corner-triangle"],
section.slide [class*="section-bar"],
section.slide [class*="section-stripe"],
section.slide [class*="closing-triangle"],
section.slide [class*="closing-bar"],
section.slide [class*="title-rule"],
section.slide [class*="title-underline"],
section.slide [class*="topbar"],
section.slide [class*="top-bar"],
section.slide hr {
  display: none !important;
}

section.slide h1, section.slide h2, section.slide h3 {
  font-family: 'DM Sans', sans-serif !important;
  font-weight: 700 !important;
  letter-spacing: -0.015em !important;
  margin-top: 0 !important;
}

section.slide h1 { font-size: 104px !important; line-height: 1.02 !important; margin-bottom: 28px !important; }
section.slide h2 { font-size: 64px !important; line-height: 1.05 !important; margin-bottom: 40px !important; }
section.slide h3 { font-size: 26px !important; line-height: 1.25 !important; font-weight: 600 !important; margin-bottom: 12px !important; }
section.slide p, section.slide li { font-size: 22px !important; line-height: 1.5 !important; }

section.slide .eyebrow,
section.slide [class*="eyebrow"],
section.slide [class*="kicker"] {
  font-size: 14px !important;
  font-weight: 600 !important;
  letter-spacing: 0.18em !important;
  text-transform: uppercase !important;
  color: #737a85 !important;
  background: transparent !important;
  border: 0 !important;
  padding: 0 !important;
  margin-bottom: 24px !important;
  display: block !important;
}
"""


BRAND_CSS_BY_PRESET: dict[str, str] = {
    "databricks-corp": DATABRICKS_CORP_BRAND_CSS,
    "databricks-corp-dark": DATABRICKS_CORP_DARK_BRAND_CSS,
    "databricks-brand": DATABRICKS_BRAND_BRAND_CSS,
    "editorial-noir": EDITORIAL_NOIR_BRAND_CSS,
    "minimal-light": MINIMAL_LIGHT_BRAND_CSS,
    "tech-graphite": TECH_GRAPHITE_BRAND_CSS,
}

_LAVA_COOL_CATEGORY_PALETTE: list[str] = [
    "#ff3621",
    "#3b6ce0",
    "#00a7b5",
    "#7c4dff",
    "#ffc043",
    "#0c8459",
    "#d34a89",
]

CATEGORY_PALETTE_BY_PRESET: dict[str, list[str]] = {
    "databricks-corp": _LAVA_COOL_CATEGORY_PALETTE,
    "databricks-corp-dark": _LAVA_COOL_CATEGORY_PALETTE,
    "databricks-brand": _LAVA_COOL_CATEGORY_PALETTE,
    "editorial-noir": [
        "#ff8c42",
        "#e8c547",
        "#c95466",
        "#7a9eaf",
        "#3d5266",
        "#9b7e5e",
        "#5e8068",
    ],
    "minimal-light": [
        "#3478f6",
        "#5856d6",
        "#34c759",
        "#ff9500",
        "#af52de",
        "#ff3b30",
        "#5ac8fa",
    ],
    "tech-graphite": [
        "#00d4aa",
        "#7fb3ff",
        "#ffc857",
        "#d29bff",
        "#ff7b9c",
        "#5ec4dd",
        "#94d35f",
    ],
}


def get_brand_css(preset_id: str | None) -> str | None:
    """Return brand CSS for the given preset id, or None if no override."""
    if not preset_id:
        return None
    return BRAND_CSS_BY_PRESET.get(preset_id)


def inject_brand_css(html: str, brand_css: str) -> str:
    """Append brand CSS to the deck's first <style> block (or wrap one)."""
    if not brand_css:
        return html
    if "<style" in html:
        return html.replace(
            "</style>",
            "\n" + brand_css + "\n</style>",
            1,
        )
    if "<head>" in html:
        return html.replace(
            "<head>",
            f"<head>\n<style>{brand_css}</style>",
            1,
        )
    return f"<style>{brand_css}</style>\n{html}"
