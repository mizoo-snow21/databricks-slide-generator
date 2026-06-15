"""Built-in starter templates exposed as a preset gallery.

The frontend can call GET /api/templates/presets to list these, then
POST /api/templates with one of the payloads (or from-preset/<id>) to
materialize the preset as a real template owned by the user.
"""

from __future__ import annotations

from typing import Any


PRESETS: list[dict[str, Any]] = [
    {
        "id": "databricks-corp",
        "name": "Databricks Corporate",
        "description": "Official corporate template — warm canvas, Oat Black top bar, Lava accent, DM Sans. For Databricks employees.",
        "tokens": {
            "palette": {
                "bg": "#f5f3f0",
                "text": "#1b3139",
                "accent": "#ff3621",
                "muted": "#6b7280",
            },
            "fonts": {
                "display": "'DM Sans', sans-serif",
                "body": "'DM Sans', sans-serif",
            },
            "typeScale": {"hero": 200, "title": 96, "body": 36, "caption": 20},
            "spacing": {"padding": 100, "gap": 40},
            "radius": 4,
        },
        "theme_markdown": (
            "Official Databricks corporate slide template. Faithful port of the FE-internal "
            "PowerPoint deck used for QBRs, customer presentations, and external talks.\n\n"
            "## Layout invariants (every light slide)\n"
            "- 8px solid bar of #1b3139 (Oat Black) running across the very top of every "
            '  *light-mode* slide. Use a `<div class="slide-topbar">` (height 8px, full width).\n'
            "- Footer at the bottom of every slide except cover/closing/section: "
            "  Databricks logo (light SVG) at lower-right, page number, and the line "
            '  "Databricks Inc. — All rights reserved". Logo URL: `/databricks-logo-light.svg` '
            "  for dark backgrounds, `/databricks-logo-dark.svg` for light backgrounds.\n"
            "- Body type: 36px DM Sans regular. Title: 96px DM Sans bold. Hero number: 200px+ bold.\n"
            "- Background: #f5f3f0 (warm cream, NOT pure white) for content slides; "
            "  #1b3139 (Oat Black) for cover/section/callout/quote/closing.\n"
            "- Accent (#ff3621 / Lava): use sparingly — only on hero numbers, eyebrow tags, "
            "  one accent rule, accent triangles on the title slide. Never as bg.\n"
            "- Asterisk-wrapped phrases in titles render in accent: **the entire data estate**.\n\n"
            "## Slide vocabulary (pick the shape that matches the content)\n"
            "Every piece of information has a shape. Match content to layout — don't default "
            "to bullets:\n"
            "- **Sequential** (steps, phases, process): `timeline`, `agenda`, `cards`\n"
            "- **Comparative** (A vs B, trade-offs): `two-column`, `pros-cons`, `comparison`\n"
            "- **Categorical** (features, pillars): `icon-grid`, `three-column`, `three-column-icons`\n"
            "- **Emphatic** (one big stat / one bold claim): `big-number`, `callout`\n"
            "- **Evidence** (proof, credibility): `quote`, `logos`, `stat-row`\n"
            "- **Status** (progress, done/not done): `checklist`\n"
            "- **Mixed content** (text + visual): `card-left`, `card-right`, `card-full`\n\n"
            "## Rhythm (cross-slide design)\n"
            "- Cover (dark) → content (light) → section break (dark) → content cluster → "
            "  big-number or callout (dark) → content → closing (dark).\n"
            "- Never repeat the same layout 3+ times in a row.\n"
            "- Dense slides (lots of bullets) need breathing room nearby (callout, big-number, "
            "  or section). Section slides create natural topic transitions.\n"
            "- Section/title/callout/quote/closing slides flip to dark bg for impact.\n\n"
            "## Content rules\n"
            "- Titles ≤ 8 words, action-oriented.\n"
            "- Bullets: 3–5 per slide, ≤ 12 words each, one idea per slide.\n"
            "- Use callout/big-number at key moments — one per major section.\n"
            "- Speaker notes welcome; render visually only the lead idea.\n"
            '- Footer text "Databricks Inc. — All rights reserved" + page number on every '
            "  non-cover slide."
        ),
        "structure_hint": (
            "Cover (title, dark, accent triangles, logo) → Agenda (numbered hexagons) → "
            "Section break (dark) → Content cluster (mix of cards / two-column / icon-grid) → "
            "Big-number or callout (dark, breathing room) → Detail (timeline or stat-row) → "
            "Quote or logos (evidence) → Closing (dark, contact / CTA, logo)"
        ),
        "style_notes": (
            "Top bar 8px Oat Black on every light slide. Footer with Lava logo + "
            '"Databricks Inc. — All rights reserved" + page number. DM Sans throughout '
            "(load via Google Fonts in deck <head>). Accent words wrapped in **asterisks** "
            "render in Lava red. Never use pure white bg — use #f5f3f0. Dark slides for "
            "title / section / callout / quote / closing only. 25 slide types available — "
            "match content shape, don't default to bullets."
        ),
    },
    {
        "id": "databricks-corp-dark",
        "name": "Databricks Corporate Dark",
        "description": "Official corporate template (dark mode) — Oat Black canvas, white ink, Lava + amber accents, DM Sans. For high-impact title/section/callout pages or all-dark decks.",
        "tokens": {
            "palette": {
                "bg": "#1b3139",
                "text": "#ffffff",
                "accent": "#ff3621",
                "muted": "#e5e7eb",
            },
            "fonts": {
                "display": "'DM Sans', sans-serif",
                "body": "'DM Sans', sans-serif",
            },
            "typeScale": {"hero": 200, "title": 96, "body": 36, "caption": 20},
            "spacing": {"padding": 100, "gap": 40},
            "radius": 4,
        },
        "theme_markdown": (
            "Official Databricks corporate template — dark mode. Same brand DNA as "
            "the light Corporate preset (DM Sans, accent triangles on title, footer "
            "with logo + 'Databricks Inc. — All rights reserved' + page number) but "
            "the entire deck runs on the Oat Black canvas instead of warm cream.\n\n"
            "## Layout invariants\n"
            "- Background: var(--osd-bg) = #1b3139 (Oat Black). Text: white. Logo: "
            "  use /databricks-logo-light.svg (the white-on-dark variant) at the "
            "  lower-right of every non-cover slide.\n"
            "- A single 8px Lava (#ff3621) bar can run along the top as a subtle "
            "  brand line, optional. The white logo + footer line still anchors the "
            "  composition.\n"
            "- Use the secondary amber accent (#f5a623) sparingly for trend-up "
            "  metrics or callout highlights; reserve Lava for the most important "
            "  one-of accent.\n\n"
            "## Slide vocabulary (dark mode considerations)\n"
            "- Title / section / callout / quote / closing: native dark — no flip needed.\n"
            "- Content / two-column / icon-grid / cards: dark cards with thin white "
            "  rules at 12% opacity, white type at 90% opacity for body, full-white "
            "  for headlines.\n"
            "- Big-number / stat-row: hero numbers in Lava or amber for impact, "
            "  labels in muted white.\n"
            "- Pros-cons: green (#10b981) for pros header, red (#ef4444) for cons "
            "  header, both on the dark canvas.\n\n"
            "## Rhythm\n"
            "- An all-dark deck loses the bright/dark contrast tool; lean on layout "
            "  variety (timeline → stat-row → callout → cards) and one Lava-accented "
            "  big-number per major section to create rhythm.\n\n"
            "## Content rules\n"
            "- Same as light: titles ≤ 8 words, bullets 3-5 / ≤ 12 words, one idea "
            "  per slide. Asterisk-wrap accent phrases (`**phrase**`) for inline Lava."
        ),
        "structure_hint": (
            "Cover (dark, Lava accent triangles, white logo) → Agenda (numbered) → "
            "Section break → Content cluster (cards / two-column / timeline) → "
            "Big-number (Lava) → Detail (stat-row) → Quote or logos → Closing"
        ),
        "style_notes": (
            "All slides on Oat Black canvas. Use /databricks-logo-light.svg (white). "
            "DM Sans throughout. Asterisk-wrapped accent words → Lava. Amber "
            "(#f5a623) reserved for secondary highlight (trend-up metric, "
            "secondary callout). Pros header green (#10b981), cons header red "
            "(#ef4444). Never use a pure black bg — always #1b3139."
        ),
    },
    {
        "id": "databricks-brand",
        "name": "Databricks Brand",
        "description": "Lava red on white. Crisp, executive, on-brand.",
        "tokens": {
            "palette": {
                "bg": "#ffffff",
                "text": "#1b3139",
                "accent": "#ff3621",
                "muted": "#6f7989",
            },
            "fonts": {
                "display": "'DM Sans', sans-serif",
                "body": "'DM Sans', sans-serif",
            },
            "typeScale": {"hero": 180, "title": 84, "body": 32, "caption": 22},
            "spacing": {"padding": 120, "gap": 48},
            "radius": 4,
        },
        "theme_markdown": (
            "Databricks brand: pure white background, Oat Black ink, Lava red as the only "
            "accent (used sparingly on key numbers, eyebrow tags, and one accent rule). "
            "DM Sans display, generous tracking. Layout is grid-disciplined — heavy use of "
            "thin rules, monospaced micro-text for IDs and metadata, no decorative gradients. "
            "Executive QBR tone."
        ),
        "structure_hint": "Title → KPIs → Trend → Detail → Insights → Actions → Closing",
        "style_notes": "One bold metric per slide. Caption in DM Mono.",
    },
    {
        "id": "editorial-noir",
        "name": "Editorial Noir",
        "description": "Dark editorial with hot orange accent. Magazine-grade.",
        "tokens": {
            "palette": {
                "bg": "#0a0a0a",
                "text": "#f6f3ec",
                "accent": "#ff4f1a",
                "muted": "#8a8a8a",
            },
            "fonts": {
                "display": "'Inter', sans-serif",
                "body": "'Inter', sans-serif",
            },
            "typeScale": {"hero": 200, "title": 88, "body": 36, "caption": 24},
            "spacing": {"padding": 120, "gap": 48},
            "radius": 0,
        },
        "theme_markdown": (
            "Editorial monochrome with one hot accent. Inter display, generous tracking on "
            "display weights, body left-aligned, no centered paragraphs. One idea per page, "
            "asymmetric grids, lots of negative space."
        ),
        "structure_hint": "Cover → Big number → Story arc → Quote → Closing",
        "style_notes": "Allow a single oversized hero number per section.",
    },
    {
        "id": "minimal-light",
        "name": "Minimal Light",
        "description": "Stark white, ink black, single blue accent. Quiet.",
        "tokens": {
            "palette": {
                "bg": "#fafafa",
                "text": "#1a1a1a",
                "accent": "#0066cc",
                "muted": "#8c8c8c",
            },
            "fonts": {
                "display": "'Inter', sans-serif",
                "body": "'Inter', sans-serif",
            },
            "typeScale": {"hero": 144, "title": 72, "body": 28, "caption": 20},
            "spacing": {"padding": 100, "gap": 40},
            "radius": 8,
        },
        "theme_markdown": (
            "Minimalist scandinavian palette. Off-white background, near-black text, one cool "
            "blue accent. Soft 8px corners on cards. Tight type, calm density, plenty of "
            "whitespace."
        ),
        "structure_hint": "Cover → Section break → Content → Numbers → Closing",
        "style_notes": "No decorative bars or gradients; rely on type and spacing.",
    },
    {
        "id": "tech-graphite",
        "name": "Tech Graphite",
        "description": "Graphite gray, mint accent, mono micro-type. Engineering-flavored.",
        "tokens": {
            "palette": {
                "bg": "#1a1d23",
                "text": "#e8eaed",
                "accent": "#00a972",
                "muted": "#737a85",
            },
            "fonts": {
                "display": "'DM Sans', sans-serif",
                "body": "'DM Sans', sans-serif",
            },
            "typeScale": {"hero": 160, "title": 72, "body": 30, "caption": 22},
            "spacing": {"padding": 96, "gap": 40},
            "radius": 6,
        },
        "theme_markdown": (
            "Engineering-toned dark theme. Graphite background, mint/seafoam accent for KPIs "
            "trending up, charts and metrics treated like terminal readouts. DM Mono used for "
            "captions, IDs, and numerical annotations."
        ),
        "structure_hint": "Header → Metrics grid → Charts → Tables → Notes",
        "style_notes": "Use thin top borders on metric cards; never round buttons more than 6px.",
    },
]


def get_preset(preset_id: str) -> dict[str, Any] | None:
    for p in PRESETS:
        if p["id"] == preset_id:
            return p
    return None
