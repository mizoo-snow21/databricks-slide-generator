"""LLM composition: build prompts and parse slide-spec responses."""

from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx

from models import ChartAugmentation, ChartDesign, TemplateGuidelines, WidgetInfo

SLIDE_AUTHORING_RULES = """
## Open-slide slide authoring rules

- **Canvas**: Fixed **1920×1080** CSS pixels per slide. Do not use viewport units (`vw`, `vh`, `%`) for layout; use px so the deck exports predictably.
- **Vertical budget**: Keep content within 1080px height. Content beyond the vertical budget is **silently cropped** in the viewer—design so headlines and body fit; prefer tightening type or content over overflowing. For each slide, mentally tally the vertical space used: padding (100–160px top + bottom) + topbar (8px) + eyebrow + heading + content blocks + footer-text reservation (CSS `::after` reserves bottom 28–48px). The remaining content area is roughly **800–900px**. If content exceeds this, REDUCE word count or DROP the lowest-priority element. Don't shrink fonts below the type scale. After drafting each slide, re-read it and ask: would this fit in 1920×1080 at 100% scale? If you stacked the elements and the total height is ≥ 1080, cut content. The viewer crops silently — there's no warning.
- **Type scale**: Follow the token CSS variables for hierarchy (`--osd-type-hero`, etc.); avoid ad-hoc font sizes unless necessary for a one-off emphasis.
- **Padding**: Target **100px–160px** inset from slide edges (align with `--osd-padding` when present).
- **Design tokens as CSS variables**: Inject and use at minimum:
  - `--osd-bg`, `--osd-text`, `--osd-accent`, `--osd-muted`
  - `--osd-font-display`, `--osd-font-body`
  - Type scale and spacing/radius variables as provided in the token block.
- **Editable elements**: Every user-editable element MUST include a stable `data-osd-id` attribute.
- **Color contract — NON-NEGOTIABLE**:
  - Never hardcode `#fff`, `#ffffff`, `white`, `#000`, `#000000`, or `black` in CSS. Always use `var(--osd-bg)`, `var(--osd-text)`, `var(--osd-accent)`, or `var(--osd-muted)`.
  - The canonical readable pairing is `background: var(--osd-bg); color: var(--osd-text)`.
  - For dramatic accent slides, set `background: var(--osd-text)` (or `var(--osd-accent)`) AND `color: var(--osd-bg)` together — never one without the other. White-text-on-default-bg slides are a contract violation: the deck preset may be light-themed and the text becomes invisible.
  - The `body` element MUST use `background: var(--osd-bg)` (or a token-derived value) — never a hardcoded gray.
  - **Dominance, not equality**: One color dominates 60-70% of every slide (the canvas — `--osd-bg` for light slides, `--osd-text` for dark). One supporting color (text). One accent (`--osd-accent` Lava — used SPARINGLY: hero numbers, eyebrows, ONE accent rule, ONE highlighted phrase per slide max). Never use 3+ accent colors equal weight — the slide reads as flat.
- **Forbidden** (do not output): `<script>`, `<iframe>`, `<link>`, `<meta>`, `<form>`, `<object>`, `<embed>`, inline event handlers (`on*`), `javascript:` URLs, or external URLs in `img` `src` or CSS `url()` (use `data:` if images are needed).
- **Inline SVG chart / legend safety** (line/bar/area, including beside `widget-chart` content): **Clip labels to the chart-area width** — any `<text>` used as a chart legend or axis label MUST NOT extend past the `chart-area` right edge. Either (a) place legends in a separate legend container ABOVE or BELOW the chart (not hugging the final data point on the right), or (b) give `chart-area` **`padding-right: 80px`** (or equivalent) so right-edge text stays in-bounds. **Never** anchor a `<text>` at the **final** data point with `text-anchor="start"` — the label width overflows. Use `text-anchor="end"` with right padding, or render the legend separately.

## Content shape → layout (don't default to bullets)

Every piece of information has a shape. Identify the shape first, THEN pick the layout. Bullets are one option among many — don't default to them.

| Shape | What it looks like | Use this layout |
|-------|--------------------|-----------------|
| Sequential | steps, phases, process, workflow | timeline, agenda, cards |
| Comparative | A vs B, options, trade-offs | two-column, pros-cons, comparison |
| Categorical | features, types, capabilities, pillars | icon-grid, three-column, three-column-icons |
| Emphatic | one key stat, one bold claim | big-number, callout |
| Evidence | proof, credibility, testimonial | quote, logos, stat-row |
| Status | progress, done/not done | checklist |
| Mixed | text + visual/diagram | card-left, card-right, card-full |

If you're about to make your third bullet slide in a row, STOP and ask: what shape does this information actually have?

## Slide type templates (use these layouts — pick by content shape)

Each `<section class="slide" data-slide-id="...">` MUST visibly resemble ONE of these layouts. Use the listed layout name as a `data-layout` attribute on the section so the post-processor can validate.

**Required attribute pattern (every slide):**

```html
<section class="slide" data-layout="title" data-slide-id="slide-01" data-osd-id="el-cover">
  <!-- content -->
</section>
```

The `data-layout="<name>"` attribute is REQUIRED on every section. Pick the name from the catalog below. The post-processor uses this to validate and to enable inspector-driven editing. Sections without `data-layout` get coerced to "content" — which is almost never right.

**Required footer (every slide except cover/closing/section):**

```html
<footer class="deck-footer">
  <img src="/databricks-logo-light.svg" alt="Databricks" class="deck-logo" />
  <span class="footer-text">Databricks Inc. — All rights reserved</span>
  <span class="page-number">3</span>
</footer>
```

Use `/databricks-logo-light.svg` on light-bg slides, `/databricks-logo-dark.svg` on dark-bg slides. Do NOT render "DATABRICKS" as text — always use the `<img>` tag pointing to the SVG URL. The brand mark is the SVG, never wordmark text.

### Structural (dark bg by default — set background: var(--osd-text); color: var(--osd-bg))

- **title** — Opening cover. Big eyebrow "EYEBROW", massive headline, optional subtitle, small author/date row. **Cover headline**: **≤ 5 words on one line** (max **6** only if a `<br>` is structurally required for emphasis). At ~96pt, more than ~6 words tends to wrap into 3+ lines and **overflow** the 1080px canvas. **Cover subtitle**: **≤ 16 words**, single line preferred. The cover MUST fit the **1080px** vertical budget at 100% scale: top-bar (8px) + accent triangle area + eyebrow (24–32px) + headline (≤ ~200px) + subtitle (≤ ~80px) + meta row (≤ ~60px) ≈ **600–700px** for the stack — **NO** extra decorative blocks below the meta row. NO decorative divs without CSS — every `<div>` in the cover must have visible content OR a fully-defined clip-path/background CSS rule. Empty `<div>`s with class names like "accent-triangle" but no CSS render as gray boxes; either omit the div entirely or define the CSS shape (e.g., `clip-path: polygon(...)` + `background: var(--osd-accent)`).
- **section** — Section divider. ~120pt section number on the left, section title on the right. Sparse.
- **closing** — Final slide. "Thank you" or CTA. Centered, large.

### Bullet / textual

- **content** — Title + 3-5 bullets (max 12 words each). Use sparingly.
- **one-column** — Single narrow column (max 60ch) for prose-heavy content. No bullets.

### Multi-column / comparison

- **two-column** — Side-by-side (50/50). Each column has its own header and 3-5 items.
- **two-column-icons** — Same as two-column but each column starts with a leading icon (emoji or SVG) above its header.
- **three-column** — Three columns, equal width, optional headers + body each.
- **three-column-icons** — Same but each column has a leading icon (emoji or SVG).
- **comparison** — VS layout. Left and right labels with a center diamond/divider.
- **pros-cons** — Two columns: pros (green ✓) on left, cons (red ✗) on right.

### Cards

- **cards** — Three equal cards in a row, each with header + 3-5 items.
- **card-left** — Card on left with image/diagram, content/bullets on right.
- **card-right** — Content/bullets on left, card on right.
- **card-full** — One full-width card, large content.

### Data / metrics

- **big-number** — One hero number (e.g., "+47%") at 200px+ in accent color, label below.
- **stat-row** — Row of 3-4 stats: each value (64px bold) + label.

### Visual / sequential

- **agenda** — Numbered list with hexagon-styled bullets (1, 2, 3, ...). 4-7 items.
- **timeline** — Sequential horizontal phases or steps with title + 1-line description each.
- **icon-grid** — 3x2 or 2x3 grid of feature cards with icon + title + 1-line description.
- **checklist** — Vertical checklist of items, each with ☑ or ☐ status.

### Evidence / social proof

- **quote** — Big quote-mark, centered testimonial text, attribution below.
- **callout** — One bold statement (≤ 12 words) at 44pt+, optional source attribution.
- **logos** — Title + grid of partner/customer logos (placeholders OK).

### Section description

- **section-description** — Section title + 2-3 line description body. Light-weight section break.

Pick the layout name that matches the content shape; tag the section with `data-layout="<name>"`. Do NOT invent new layout names. If an existing layout doesn't fit, fall back to `content` or `card-full`.

## Cross-slide rhythm

A presentation is a sequence. Each slide exists in context of what came before and after.

- Don't repeat the same layout 3+ times in a row.
- Dense slides (lots of bullets, details) need breathing room nearby (callout, big-number, section break).
- Section/title/callout/quote/closing slides flip to dark bg (set background: var(--osd-text); color: var(--osd-bg)) for impact.
- Vary the visual treatment to maintain audience engagement.

## Editorial restraint (no AI-tell decorations)

This deck reads as **editorial / magazine**, not "AI generated PowerPoint". Hierarchy comes from **typography weight, size, and whitespace** — NOT from decorative chrome. Specifically, do NOT emit any of these (they will be CSS-stripped post-process anyway, but emitting them wastes prompt tokens and signals AI authorship):

- ❌ **Diagonal corner triangles** on cover / section / closing (`clip-path: polygon(...)` decorations in Lava). The cover earns its drama from a giant headline + Lava accent phrase, not corner cosmetics.
- ❌ **Vertical accent stripes / bars on the left edge** of section dividers or content slides. The section divider earns its drama from a bold big section title, not a bar.
- ❌ **Horizontal accent rules** under titles, above eyebrows, between rows. Use **whitespace** and **type weight contrast** instead.
- ❌ **Top bars / page-edge bars** of any color. The slide canvas itself is the chrome.
- ❌ **"01" / "02" / "03" giant section numerals** as the dominant visual on a section divider. The TITLE is the dominant element; a small "section two" eyebrow is allowed but the numeral is not the hero.
- ❌ **Eyebrow tag pills** with background fills (`background: var(--osd-accent); padding: 6px 12px; border-radius: 4px`). Eyebrows are tracked uppercase text, period — no pill shape, no fill, no border.
- ❌ **Decorative empty `<div>`s** with class names like "accent-triangle", "section-bar", "title-rule" — they render as gray boxes if the CSS rule doesn't ship.

What earns its place visually:

- A **single accent-highlighted phrase** per slide (`**phrase**`), max one per slide.
- One **hero number** at 200pt+ on big-number / stat-row slides.
- Inline **SVG charts** on chart slides (line, bar, area), with the data being the visual.
- **Generous whitespace** — 120–160px slide-edge padding, 32–48px between content blocks.
- **Type weight contrast** — heavy 700-weight title vs. regular 400 body; the contrast IS the design.

The Databricks brand identity is: **Oat Black canvas + warm cream + ONE Lava accent phrase per moment + DM Sans typography**. That's it. No gimmicks.

## Content rules

- Titles: **Cover/title slides**: ≤ **5 words**. **All other slides**: ≤ 8 words, action-oriented. (Cover uses larger 96–200pt fonts and a stricter vertical budget.)
- Bullets: 3-5 per slide, max 12 words each.
- One idea per slide — don't overcrowd.
- Use callout/big-number at key moments — one per major section.

## Accent words (asterisk-wrapped)

To highlight a phrase in the accent color inline, wrap it in **double asterisks**:

> "Governance of **the entire data estate** is hard"

The post-processor converts `**phrase**` to `<span class="accent">phrase</span>` and ensures the slide CSS has `.accent { color: var(--osd-accent) }`. Use sparingly — at most one accent phrase per title.

## Avoid (common AI-generated slide tells)

These are mistakes that immediately mark a deck as low-effort or AI-generated. Do NOT do them:

- **NEVER use thin accent lines under titles** (a hallmark of AI-generated slides). Use whitespace and type weight contrast instead — NOT a side bar (also a tell).
- **Don't repeat the same layout 3+ times in a row** — vary cards, columns, and callouts across slides.
- **Don't create text-only slides** — every content slide should have at least one visual element (icon, shape, chart placeholder, divider, accent triangle).
- **Don't center body text** — left-align paragraphs and lists; center only titles, hero numbers, and callouts.
- **Don't skimp on size contrast** — titles need 60-96px to stand out from 22-30px body. Hero numbers should be 4-6× body text.
- **Don't default to blue** — pick palette colors that reflect the topic; if you're using the corp preset, lean into Lava + Oat Black, not generic blues.
- **Don't mix spacing randomly** — pick a 24px / 32px / 48px gap rhythm and use consistently within a section.
- **Don't style one slide and leave the rest plain** — commit fully or keep the whole deck simple.
- **Don't use low-contrast text** — light gray text on cream-colored backgrounds is unreadable. Body text needs `var(--osd-text)` not `var(--osd-muted)`.
- **Don't use low-contrast icons** — emoji or SVG icons on similar-tone backgrounds disappear. Use a colored circle or accent background behind icons on busy slides.
- **Don't fill every inch** — leave breathing room. 100-160px from slide edges. Empty space is intentional design, not unused real estate.

### Self-review checklist

Before finishing, verify: dimensions respect 1920×1080; no `vw`/`vh`/percent layout; tokens wired via CSS variables; every editable region has `data-osd-id`; **no hardcoded `#fff`/`white`/`#000`/`black` colors anywhere**; every slide passes the contrast contract (any `color: var(--osd-bg)` requires the parent slide's background to be `var(--osd-text)` or `var(--osd-accent)`); no forbidden tags or unsafe URLs; every section has `data-layout="<name>"` set to one of the 24 catalog layouts; every non-cover slide footer uses `<img src="/databricks-logo-{light,dark}.svg">` (NOT a "DATABRICKS" wordmark text).

## House style

**Default (when the user gives no specific style direction):** the deck should read as a polished **Databricks document** — a warm-gray **#f9f7f5** canvas, **DM Sans** for display / **DM Mono** for mono/labels, a **12-column grid** mindset for alignment, and the Databricks brand palette: **Lava #FF3621**, **Oat Black #1B3139**, cool gray **#A0ACBE**. Express this THROUGH the design tokens (`var(--osd-bg)`, `var(--osd-text)`, `var(--osd-accent)`, `var(--osd-muted)`, `--osd-font-display`, `--osd-font-body`) — the Databricks presets already encode this palette; do not hardcode the hexes when a token exists. If the active template/preset defines a different look (e.g. a dark editorial preset), follow the template — this default only applies when nothing else dictates the look.

**Consulting-firm style (ONLY when the user explicitly asks for a McKinsey / BCG / コンサル / consulting-style deck):** use a **#f9f7f5** background, **Meiryo (メイリオ)** typography, **minimal icons and decoration**, and a clean **McKinsey/BCG-style editorial layout** — strong horizontal rules, dense text-and-table slides, restrained color, lots of whitespace. **HARD RULE: never render the McKinsey logo, wordmark, or name as a brand mark anywhere in the deck.** This mode is an explicit user-requested override of the default house style (Meiryo replaces the default fonts).
""".strip()


def _tokens_to_css_vars(tokens: dict) -> str:
    """Build a multi-line CSS custom properties block from a design token dict."""
    lines: list[str] = []
    palette = tokens.get("palette") or {}
    for key, suffix in (
        ("bg", "bg"),
        ("text", "text"),
        ("accent", "accent"),
        ("muted", "muted"),
    ):
        if key in palette:
            lines.append(f"  --osd-{suffix}: {palette[key]};")
    fonts = tokens.get("fonts") or {}
    if "display" in fonts:
        lines.append(f"  --osd-font-display: {fonts['display']};")
    if "body" in fonts:
        lines.append(f"  --osd-font-body: {fonts['body']};")
    type_scale = tokens.get("typeScale") or {}
    for key in ("hero", "title", "body", "caption"):
        if key in type_scale:
            lines.append(f"  --osd-type-{key}: {int(type_scale[key])}px;")
    spacing = tokens.get("spacing") or {}
    if "padding" in spacing:
        lines.append(f"  --osd-padding: {int(spacing['padding'])}px;")
    if "gap" in spacing:
        lines.append(f"  --osd-gap: {int(spacing['gap'])}px;")
    if "radius" in tokens:
        lines.append(f"  --osd-radius: {int(tokens['radius'])}px;")
    return "\n".join(lines) + ("\n" if lines else "")


AVAILABLE_LAYOUTS = """## Available layouts (create-from-spec)

- **title**: Title slide — fields: `title`, `subtitle?`, `author?`, `date?`
- **section**: Section divider — fields: `title`, `subtitle?`
- **section-description**: Section with body — fields: `title`, `subtitle?`, `description?` or `bullets?`
- **content**: Title + bullets/body — fields: `title`, `subtitle?`, `bullets: [strings]`, `notes?`
- **one-column**: Single column — fields: `title`, `content?` or `bullets?`
- **closing**: Closing — fields: `title`, `subtitle?`
- **two-column**: Two columns — fields: `title`, `subtitle?`, `left_header?`, `left: [strings]`, `right_header?`, `right: [strings]` (or `columns: [{header, items}]`)
- **two-column-icons**: Two columns + icons — fields: `title`, `subtitle?`, `columns: [{header, items, icon?}]`
- **three-column**: Three columns — fields: `title`, `subtitle?`, `columns: [{header, items}]`
- **three-column-icons**: Three columns + icons — fields: `title`, `subtitle?`, `columns: [{header, items, icon?}]`
- **cards**: Card grid — fields: `title`, `subtitle?`, `cards: [{header, content? or items?}]`
- **card-right**: Card on right — fields: `title`, `subtitle?`, `bullets?` or `content?`, `card_content?`
- **card-left**: Card on left — fields: `title`, `subtitle?`, `card_content?`, `bullets?` or `content?`
- **card-full**: Full card / chart-friendly — fields: `title`, `subtitle?`, `content?`
- **big-number**: Hero metric — fields: `number`, `text`, `subtitle?`
- **stat-row**: KPI row — fields: `title`, `stats: [{value, label}]`
- **comparison**: Two-way compare — fields: `title`, `left_label`, `right_label`
- **pros-cons**: Pros and cons — fields: `title`, `pros_header?`, `cons_header?`, `pros: [strings]`, `cons: [strings]`
- **agenda**: Agenda list — fields: `title`, `items: [strings]`
- **timeline**: Timeline — fields: `title`, `steps: [{title, description}]`
- **icon-grid**: Icon grid — fields: `title`, `items: [{icon, title, description?}]`
- **checklist**: Checklist — fields: `title`, `items: [{text, checked: bool}]`
- **quote**: Quote — fields: `quote`, `attribution?`
- **callout**: Callout — fields: `text`, `source?`
- **logos**: Logo strip — fields: `title`, `subtitle?`, `logos: [strings]`
- **blank**: Blank slide — no content fields

For chart widgets, prefer **card-full** or **two-column** (chart-friendly layouts) and set `_widget_id` to the widget id. For two charts side-by-side, use `_left_widget_id` and `_right_widget_id` where the spec allows. Table values often use a `table` object with `data`, `y`, `width`, `height`.
"""


def build_prompt(
    widgets: list[WidgetInfo],
    guidelines: TemplateGuidelines,
    dashboard_name: str,
    user_prompt: str | None = None,
) -> str:
    """Assemble the user message for slide composition."""
    lines: list[str] = []
    for w in widgets:
        cols = ", ".join(w.columns) if w.columns else "(none)"
        line = (
            f"- ID: {w.widget_id} | Title: {w.title} | Type: {w.viz_type} | "
            f"Columns: {cols} | Rows: {w.row_count}"
        )
        if w.query_result_summary:
            line += f"\n  Data summary: {w.query_result_summary}"
        lines.append(line)
    widgets_section = "\n".join(lines) if lines else "(No visualization widgets found)"

    prompt = f"""You are a presentation designer. Create a slide deck spec from a dashboard.

## Dashboard: {dashboard_name}

### Widgets available:
{widgets_section}

### Template guidelines:
- Slide count: {guidelines.total_slides_min} to {guidelines.total_slides_max}
- Structure: {guidelines.structure_hint}
- Preferred layouts: {", ".join(guidelines.preferred_layouts)}
- Style: {guidelines.style_notes}
- Must include: {", ".join(guidelines.must_include)}
- Chart preference: {guidelines.chart_preference}

{AVAILABLE_LAYOUTS}

## Instructions:
1. Analyze the dashboard widgets and create a narrative slide deck.
2. Map widgets to appropriate slides using `_widget_id` (and paired widget fields when needed).
3. Generate insightful titles and text (not only repeating widget titles).
4. Structure slides to tell a coherent story.
5. **IMPORTANT: Generate all slide text in the SAME LANGUAGE as the dashboard name and widget data.** If the dashboard name is in Japanese, write all titles, body text, and insights in Japanese. If in English, use English. Match the language of the source data.

## Fidelity rules (HARD CONSTRAINTS — do not violate)

These rules trump any other guidance. Violations are silent failures users notice immediately.

**Title & deck-level naming.** Slide titles, the deck title, and every eyebrow / label MUST be derived from the supplied widget titles, column names, and dashboard name. Do not invent metric names that are not present in the metadata. Examples of phrases you must NEVER write unless they appear literally in widget titles or columns: "workload volume", "platform health", "sender reputation", "data platform performance", "quarter-over-quarter growth" — these are generic QBR clichés. Use the actual subject of the dashboard.

**Numeric content.** On `big-number`, `stat-row`, `callout`, and any other layout with numeric slots:
- If a widget has a `query_result_summary` field, you MAY quote a number from it verbatim — but never paraphrase into a different number or rounding.
- Without `query_result_summary`, do NOT invent a numeric value. Instead, render the slot as the column/expression name in monospaced caps (e.g., `DELIVERY_RATE`, `OPENS_RATE`), or write "—" if there is no defensible literal.
- Percentage signs, deltas (+X%), and currency symbols on fabricated values are forbidden.

**Widget citation.** Every reference to widget data in slide markup MUST include the widget id in `<div class="stat-id">` or a similar visible citation slot, using the literal format `<widget-id> · <expression>` where `<expression>` is taken from that widget's `columns` list or `title`. Do not fabricate expression names.

**No generic QBR template.** Frame slides around the actual dashboard subject. If the dashboard is about marketing campaigns, the deck title and section headings must reflect marketing-campaign vocabulary, not "Data Platform Review".
6. Output ONLY a JSON array in create-from-spec format. No other text."""

    if user_prompt:
        prompt += f"""

## User direction:
{user_prompt}"""

    return prompt


def _format_widgets_for_prompt(
    widgets: list[WidgetInfo], chart_ids: list[str] | None = None
) -> str:
    chart_set = set(chart_ids or [])
    lines: list[str] = []
    for w in widgets:
        cols = ", ".join(w.columns) if w.columns else "(none)"
        chart_flag = (
            " | **CHART READY → embed via data-widget-id**"
            if w.widget_id in chart_set
            else ""
        )
        line = (
            f"- ID: `{w.widget_id}` | Title: {w.title} | Type: {w.viz_type} | "
            f"Columns: {cols} | Rows: {w.row_count}{chart_flag}"
        )
        if w.query_result_summary:
            line += f"\n  Data summary: {w.query_result_summary}"
        lines.append(line)
    return "\n".join(lines) if lines else "(No visualization widgets found)"


_DEFAULT_SERVING_ENDPOINT = "databricks-claude-sonnet-4-6"

# 429 retry: first attempt with 0s wait, then exponential backoff. Sized so a
# transient per-principal rate limit clears within ~30s without re-prompting.
_LLM_RATE_LIMIT_BACKOFF_S: tuple[float, ...] = (0.0, 3.0, 8.0, 20.0)


def _endpoint_supports_temperature(endpoint: str) -> bool:
    """Some Foundation Model endpoints reject the `temperature` param:
    GPT-5 family (5.0/5.4/5.5/5.5-pro) and Claude Opus 4.7 (and newer)."""
    ep_lower = endpoint.lower()
    return not ("gpt-5" in ep_lower or "opus-4-7" in ep_lower)


class LLMService:
    def __init__(self, workspace_client: Any = None) -> None:
        import os

        self._client = workspace_client
        endpoint = (
            os.environ.get("SERVING_ENDPOINT") or _DEFAULT_SERVING_ENDPOINT
        ).strip()
        # Editor-time operations (comment apply, slide regen/add) use a lighter
        # endpoint to avoid hitting per-principal rate limits on Opus during
        # iterative editing. Falls back to the main endpoint if not set.
        edit_endpoint = (os.environ.get("EDIT_SERVING_ENDPOINT") or endpoint).strip()
        self._endpoint = endpoint
        self._edit_endpoint = edit_endpoint
        self._serving_invocations_path = f"/serving-endpoints/{endpoint}/invocations"
        self._supports_temperature = _endpoint_supports_temperature(endpoint)
        self._edit_supports_temperature = _endpoint_supports_temperature(edit_endpoint)

    def _build_request_body(
        self,
        messages: list[dict[str, str]],
        max_tokens: int,
        temperature: float,
        *,
        supports_temperature: bool | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "messages": messages,
            "max_tokens": max_tokens,
        }
        st = (
            self._supports_temperature
            if supports_temperature is None
            else supports_temperature
        )
        if st:
            body["temperature"] = temperature
        return body

    def _invocations_path(self, endpoint: str | None) -> str:
        ep = endpoint or self._endpoint
        return f"/serving-endpoints/{ep}/invocations"

    async def _foundation_model_chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 4096,
        temperature: float = 0.3,
        timeout_s: float = 60.0,
        endpoint: str | None = None,
    ) -> str:
        import sys

        if not self._client:
            raise RuntimeError("Workspace client required for LLM calls")

        host = self._client.config.host.rstrip("/")
        token = (
            self._client.config.authenticate()
            .get("Authorization", "")
            .replace("Bearer ", "")
        )
        ep = endpoint or self._endpoint
        supports_temp = (
            self._edit_supports_temperature
            if endpoint == self._edit_endpoint
            else self._supports_temperature
        )
        print(
            f"[llm] async chat → endpoint={ep} (main={self._endpoint}, edit={self._edit_endpoint})",
            file=sys.stderr,
            flush=True,
        )

        async with httpx.AsyncClient() as http:
            resp = await http.post(
                f"{host}{self._invocations_path(endpoint)}",
                headers={"Authorization": f"Bearer {token}"},
                json=self._build_request_body(
                    messages,
                    max_tokens,
                    temperature,
                    supports_temperature=supports_temp,
                ),
                timeout=timeout_s,
            )
            resp.raise_for_status()
            data = resp.json()

        choices = data.get("choices", [])
        if not choices:
            raise ValueError("LLM endpoint returned no choices")
        return choices[0].get("message", {}).get("content", "")

    def _foundation_model_chat_sync(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 4096,
        temperature: float = 0.3,
        timeout_s: float = 240.0,
        endpoint: str | None = None,
    ) -> str:
        import sys

        if not self._client:
            raise RuntimeError("Workspace client required for LLM calls")

        host = self._client.config.host.rstrip("/")
        token = (
            self._client.config.authenticate()
            .get("Authorization", "")
            .replace("Bearer ", "")
        )
        ep = endpoint or self._endpoint
        supports_temp = (
            self._edit_supports_temperature
            if endpoint == self._edit_endpoint
            else self._supports_temperature
        )
        print(
            f"[llm] sync chat → endpoint={ep} (main={self._endpoint}, edit={self._edit_endpoint})",
            file=sys.stderr,
            flush=True,
        )

        body = self._build_request_body(
            messages, max_tokens, temperature, supports_temperature=supports_temp
        )
        url = f"{host}{self._invocations_path(endpoint)}"
        headers = {"Authorization": f"Bearer {token}"}
        with httpx.Client() as http:
            for delay in _LLM_RATE_LIMIT_BACKOFF_S:
                if delay:
                    print(
                        f"[llm] 429 backoff — sleeping {delay}s",
                        file=sys.stderr,
                        flush=True,
                    )
                    time.sleep(delay)
                resp = http.post(url, headers=headers, json=body, timeout=timeout_s)
                if resp.status_code != 429:
                    break
            # _LLM_RATE_LIMIT_BACKOFF_S is non-empty, so resp is always bound.
            resp.raise_for_status()
            data = resp.json()

        choices = data.get("choices", [])
        if not choices:
            raise ValueError("LLM endpoint returned no choices")
        return choices[0].get("message", {}).get("content", "")

    @staticmethod
    def _parse_suggested_questions(raw: str, n: int) -> list[str]:
        """Parse a newline-separated question list; strip bullets/numbering, dedupe, cap."""
        _line_prefix = re.compile(r"^\s*(?:\d+[.)]\s*|[\-*•]\s+)")
        seen: set[str] = set()
        result: list[str] = []
        for line in raw.splitlines():
            cleaned = _line_prefix.sub("", line.strip()).strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            result.append(cleaned)
            if len(result) >= n:
                break
        return result

    def suggest_questions(
        self,
        *,
        title: str,
        description: str,
        n: int = 8,
    ) -> list[str]:
        """Return up to n analytical NL questions for a Genie space."""
        desc_block = description.strip() or "(no description provided)"
        prompt = (
            f'Genie space title: "{title}"\n'
            f"Description:\n{desc_block}\n\n"
            f"Suggest up to {n} concise, analytical natural-language data-exploration "
            "questions a user could ask THIS Genie space based on its title and description.\n\n"
            "Return a plain newline-separated list of questions only — one question per line. "
            "No numbering or bullets required."
        )
        raw = self._foundation_model_chat_sync(
            [{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=0.4,
        )
        return self._parse_suggested_questions(raw, n)

    async def compose_slides(
        self,
        widgets: list[WidgetInfo],
        guidelines: TemplateGuidelines,
        dashboard_name: str,
        user_prompt: str | None = None,
    ) -> list[dict[str, Any]]:
        """Call the Foundation Model serving endpoint and return parsed slide specs."""
        prompt = build_prompt(widgets, guidelines, dashboard_name, user_prompt)
        raw_text = await self._foundation_model_chat(
            [{"role": "user", "content": prompt}]
        )
        return self._parse_response(raw_text)

    def generate_deck_outline(
        self,
        *,
        tokens: dict,
        theme_markdown: str,
        widgets: list[WidgetInfo],
        user_prompt: str = "",
        reference_doc: str | None = None,
        reference_doc_name: str | None = None,
    ) -> str:
        """Generate a deck outline as JSON: {"slides": [{layout, title, summary, notes}]}.

        Returns raw model output; caller should parse & validate.
        """
        prompt = self._build_outline_prompt(
            tokens=tokens,
            theme_markdown=theme_markdown,
            widgets=widgets,
            user_prompt=user_prompt,
            reference_doc=reference_doc,
            reference_doc_name=reference_doc_name,
        )
        return self._foundation_model_chat_sync(
            [{"role": "user", "content": prompt}], max_tokens=2048
        )

    def _build_outline_prompt(
        self,
        *,
        tokens: dict,
        theme_markdown: str,
        widgets: list[WidgetInfo],
        user_prompt: str,
        reference_doc: str | None = None,
        reference_doc_name: str | None = None,
    ) -> str:
        widget_lines = (
            "\n".join(
                f"- widget {w.widget_id} ({w.viz_type}): {w.title}"
                for w in widgets[:30]
            )
            or "  (no widgets — design from prompt + theme)"
        )
        palette = (tokens or {}).get("palette") or {}
        palette_line = (
            f"## Palette tokens (hints)\n{json.dumps(palette)}\n\n" if palette else ""
        )
        ref_section = ""
        if reference_doc is not None and reference_doc.strip():
            display_name = reference_doc_name or "(unnamed)"
            ref_section = (
                f"## Reference document: {display_name}\n\n"
                "The user provided this document as the primary content source. "
                "Read it carefully and shape the outline so each slide maps to a "
                "specific section, claim, or finding from this document. The "
                "dashboard widgets are supplementary — use them to back up the "
                "doc's claims with data, not as the primary structure.\n\n"
                "---\n"
                f"{reference_doc.strip()}\n"
                "---\n\n"
            )
        return (
            "You are designing the OUTLINE of a slide deck. Do NOT generate HTML yet — "
            "only the structure as JSON.\n\n"
            f"{palette_line}"
            f"{ref_section}"
            f"## Theme\n{theme_markdown}\n\n"
            f"## User intent\n{user_prompt or '(none)'}\n\n"
            f"## Available widgets (data sources)\n{widget_lines}\n\n"
            "## Fidelity rules (HARD CONSTRAINTS — do not violate)\n\n"
            "These rules trump any other guidance. Violations are silent failures users notice immediately.\n\n"
            '**Title & deck-level naming.** Slide titles, the deck title, and every eyebrow / label MUST be derived from the supplied widget titles, column names, and dashboard name. Do not invent metric names that are not present in the metadata. Examples of phrases you must NEVER write unless they appear literally in widget titles or columns: "workload volume", "platform health", "sender reputation", "data platform performance", "quarter-over-quarter growth" — these are generic QBR clichés. Use the actual subject of the dashboard.\n\n'
            "**Numeric content.** On `big-number`, `stat-row`, `callout`, and any other layout with numeric slots:\n"
            "- If a widget has a `query_result_summary` field, you MAY quote a number from it verbatim — but never paraphrase into a different number or rounding.\n"
            '- Without `query_result_summary`, do NOT invent a numeric value. Instead, render the slot as the column/expression name in monospaced caps (e.g., `DELIVERY_RATE`, `OPENS_RATE`), or write "—" if there is no defensible literal.\n'
            "- Percentage signs, deltas (+X%), and currency symbols on fabricated values are forbidden.\n\n"
            '**Widget citation.** Every reference to widget data in slide markup MUST include the widget id in `<div class="stat-id">` or a similar visible citation slot, using the literal format `<widget-id> · <expression>` where `<expression>` is taken from that widget\'s `columns` list or `title`. Do not fabricate expression names.\n\n'
            '**No generic QBR template.** Frame slides around the actual dashboard subject. If the dashboard is about marketing campaigns, the deck title and section headings must reflect marketing-campaign vocabulary, not "Data Platform Review".\n\n'
            "## Output\n"
            "Return ONLY a JSON object (no markdown fences, no prose). Schema:\n"
            '{"slides": [{"layout": "<one of: title section closing content one-column '
            "two-column two-column-icons three-column three-column-icons comparison pros-cons cards "
            "card-left card-right card-full big-number stat-row agenda timeline "
            'icon-grid checklist quote callout logos section-description>", '
            '"title": "<≤8 words>", "summary": "<≤25 words explaining the slide content>", '
            '"notes": "<optional speaker notes>"}]}\n\n'
            "## Design rules\n"
            "- 5 to 10 slides total. Aim for 7.\n"
            "- First slide ALWAYS layout=title (cover); last ALWAYS layout=closing.\n"
            "- Use a section divider every 3-4 content slides.\n"
            "- Don't repeat the same layout 3+ times in a row.\n"
            "- Pick layout to match content shape:\n"
            "  - sequential (steps, phases) → timeline / agenda / cards\n"
            "  - comparative → two-column / pros-cons / comparison\n"
            "  - categorical (features) → icon-grid / three-column\n"
            "  - emphatic (one big stat) → big-number / callout\n"
            "  - evidence (proof, quote) → quote / logos / stat-row\n"
            "- Include at least one big-number or callout for impact.\n"
            "- Every slide title ≤ 8 words. Every summary ≤ 25 words.\n\n"
            "Return JSON only."
        )

    def generate_deck_html(
        self,
        *,
        tokens: dict,
        theme_markdown: str,
        widgets: list[WidgetInfo],
        user_prompt: str | None = None,
        widget_chart_ids: list[str] | None = None,
        outline: list[dict] | None = None,
    ) -> str:
        import sys

        prompt = self._build_deck_html_prompt(
            tokens=tokens,
            theme_markdown=theme_markdown,
            widgets=widgets,
            user_prompt=user_prompt or "",
            widget_chart_ids=widget_chart_ids or [],
            outline=outline,
        )
        print(
            f"[llm] generate_deck_html prompt len={len(prompt)} chart_ids={len(widget_chart_ids or [])}",
            file=sys.stderr,
            flush=True,
        )
        print(
            f"[llm] CHART RENDERING in prompt: {'⚡ CHART RENDERING' in prompt}",
            file=sys.stderr,
            flush=True,
        )
        return self._foundation_model_chat_sync(
            [{"role": "user", "content": prompt}], max_tokens=16384
        )

    def rewrite_element(
        self,
        *,
        target_outer_html: str,
        slide_excerpt: str,
        tokens: dict,
        theme_markdown: str,
        note: str,
    ) -> str:
        prompt = self._build_rewrite_element_prompt(
            target_outer_html=target_outer_html,
            slide_excerpt=slide_excerpt,
            tokens=tokens,
            theme_markdown=theme_markdown,
            note=note,
        )
        return self._foundation_model_chat_sync(
            [{"role": "user", "content": prompt}], endpoint=self._edit_endpoint
        )

    def generate_slide_section(
        self,
        *,
        deck_html: str,
        tokens: dict,
        theme_markdown: str,
        user_prompt: str,
    ) -> str:
        prompt = self._build_add_slide_prompt(
            deck_html=deck_html,
            tokens=tokens,
            theme_markdown=theme_markdown,
            user_prompt=user_prompt,
        )
        return self._foundation_model_chat_sync(
            [{"role": "user", "content": prompt}], endpoint=self._edit_endpoint
        )

    def regenerate_slide_section(
        self,
        *,
        deck_html: str,
        slide_outer_html: str,
        tokens: dict,
        theme_markdown: str,
        feedback: str = "",
    ) -> str:
        """Regenerate a single slide section, preserving its data-slide-id.

        Returns the new <section class="slide"> outerHTML (single root).
        """
        prompt = self._build_regenerate_slide_prompt(
            _deck_html=deck_html,
            slide_outer_html=slide_outer_html,
            tokens=tokens,
            theme_markdown=theme_markdown,
            feedback=feedback,
        )
        return self._foundation_model_chat_sync(
            [{"role": "user", "content": prompt}], endpoint=self._edit_endpoint
        )

    def audit_deck(
        self,
        *,
        deck_html: str,
        tokens: dict,
        theme_markdown: str,
    ) -> str:
        """Audit a generated deck and return JSON: {issues: [...]}.

        Caller parses; empty issues list = clean deck.
        """
        prompt = self._build_audit_prompt(
            deck_html=deck_html,
            tokens=tokens,
            theme_markdown=theme_markdown,
        )
        return self._foundation_model_chat_sync(
            [{"role": "user", "content": prompt}], max_tokens=2048
        )

    def _build_audit_prompt(
        self,
        *,
        deck_html: str,
        tokens: dict,
        theme_markdown: str,
    ) -> str:
        css_vars = _tokens_to_css_vars(tokens)
        return (
            "You are a design QA auditor. Find issues in this deck.\n\n"
            "ASSUME there are problems — your job is to find them. "
            "If you find zero issues on first inspection, you weren't looking hard enough.\n\n"
            f"## Theme\n{theme_markdown}\n\n"
            "## Design tokens\n"
            f"```css\n:root {{\n{css_vars}\n}}\n```\n\n"
            "## Deck HTML\n"
            f"```html\n{deck_html[:14000]}\n```\n\n"
            "## What to check\n"
            "- Repeated layouts 3+ in a row\n"
            "- Text-only slides without any visual element\n"
            "- Hardcoded colors (#fff, #000, white, black)\n"
            "- Low-contrast text (e.g. muted on similar bg)\n"
            "- Missing data-layout attribute on a section.slide\n"
            "- Cover (title) slide that's NOT dark when corp brand demands it\n"
            "- Long titles (> 8 words) or > 5 bullets per slide\n"
            "- Centered body text (only titles/callouts may center)\n"
            "- Empty decorative divs without CSS shape rules\n"
            "- Bullets > 12 words\n"
            "- Content slide with same layout as adjacent slide\n\n"
            "## Slide-deck design checklist (P1 unless stated)\n"
            "For each slide AND the overall sequence, also flag:\n"
            "1. **Content shape mismatch (P1)** — does the slide's layout match "
            "the shape of its content (Sequential/Comparative/Categorical/Emphatic/"
            "Evidence/Status/Mixed per the rules above)? Wrong layout = P1.\n"
            "2. **Layout repetition (P1)** — same data-layout used 3+ times in a row "
            "across the deck. Flag the offending slides as P1.\n"
            "3. **Missing rhythm (P2)** — long runs (5+) of light slides without a dark "
            "accent (callout/big-number/section/quote/title) for visual breathing room.\n"
            "4. **Section transitions (P2)** — does each major topic boundary have a "
            "`section` divider? If a deck spans 3+ logical groups but has 0 section "
            "dividers, flag as P2.\n"
            "5. **Moments of impact (P2)** — at least one big-number, callout, or quote "
            "should appear in the deck for emphatic value. None = P2 on deck-level "
            "(use the FIRST content slide_id as anchor).\n\n"
            "## Visual rendering checklist (assume issues exist — find them)\n\n"
            "For each slide, also flag these as P1:\n"
            "- **Overlapping elements** — text through shapes, lines through words, stacked items at the same coordinates\n"
            "- **Text overflow** — content cut off at section boundaries OR at the 1080px canvas edge\n"
            "- **Decorative lines mis-positioned** — a single-line accent rule positioned where the title actually wraps to two lines (rule appears mid-title)\n"
            "- **Footer collision** — bottom-row content (footer text, page number, source attribution) overlapping with body content above\n"
            '- **Cramped spacing** — elements within 0.3" of each other when they should breathe; or one section is dense while another has dead empty space\n'
            '- **Insufficient slide margins** — < 0.5" inset from canvas edges (use 100-160px / 1.0-1.6")\n'
            "- **Misaligned columns** — column dividers, headers, or content blocks not on the same vertical baseline\n"
            "- **Low-contrast text** — e.g., light gray text on cream/light background; light text on light bg; dark icons on dark bg without contrasting circle\n"
            "- **Excessive text wrapping** — text box width too narrow, causing the same paragraph to wrap 4+ times\n"
            '- **Leftover placeholder text** — strings like "Lorem ipsum", "xxxx", "Replace with...", "Click to add", "Tap to enter" — these mean a corporate-template placeholder leaked through unfilled\n\n'
            "For the slide_id of cross-slide issues (rhythm, motif), use the FIRST content slide's slide_id as anchor.\n\n"
            "## Output\n"
            "Return ONLY a JSON object. Schema:\n"
            '{"issues": [{"slide_id": "<the data-slide-id>", '
            '"severity": "<P0 | P1 | P2>", '
            '"message": "<concise 1-line description of the issue>", '
            '"fix_hint": "<concrete suggestion for how to fix it>"}]}\n\n'
            'List 0-10 issues. Be specific. If the deck is genuinely clean, return {"issues": []}.\n'
            "Return JSON only — no markdown fences, no prose."
        )

    def _build_regenerate_slide_prompt(
        self,
        *,
        _deck_html: str,
        slide_outer_html: str,
        tokens: dict,
        theme_markdown: str,
        feedback: str,
    ) -> str:
        css_vars = _tokens_to_css_vars(tokens)
        return (
            "You are regenerating a SINGLE slide in an existing deck.\n\n"
            f"## Theme\n{theme_markdown}\n\n"
            "## Design tokens (CSS variables to use)\n"
            f"```css\n:root {{\n{css_vars}\n}}\n```\n\n"
            f"## Current slide\n```html\n{slide_outer_html}\n```\n\n"
            f"## User feedback\n{feedback or '(no specific feedback — improve it; consider better layout, tighter copy, stronger visual hierarchy)'}\n\n"
            "## Rules (NON-NEGOTIABLE)\n"
            '- Output a SINGLE `<section class="slide" data-slide-id="..." data-osd-id="..." data-layout="...">` element — no surrounding tags, no <html>/<body>.\n'
            "- PRESERVE the existing data-slide-id from the current slide.\n"
            "- Update data-layout if changing the slide type.\n"
            "- Use only `var(--osd-bg)`, `var(--osd-text)`, `var(--osd-accent)`, `var(--osd-muted)` for colors. NEVER hardcode #fff/#000/white/black.\n"
            "- Honor the theme markdown's brand voice and the layout vocabulary "
            "(title/section/closing/content/two-column/two-column-icons/three-column/three-column-icons/"
            "comparison/pros-cons/cards/card-{left,right,full}/big-number/stat-row/agenda/"
            "timeline/icon-grid/checklist/quote/callout/logos/section-description).\n"
            "- For accent words within text, wrap in **double asterisks**.\n"
            "- 1920×1080 px; padding 100-160px from edges.\n"
            "- Output the full <section> outerHTML, ready to drop into the deck."
        )

    def html_to_spec_json(self, *, deck_html: str) -> str:
        prompt = self._build_html_to_spec_prompt(deck_html=deck_html)
        return self._foundation_model_chat_sync([{"role": "user", "content": prompt}])

    def _build_deck_html_prompt(
        self,
        *,
        tokens: dict,
        theme_markdown: str,
        widgets: list[WidgetInfo],
        user_prompt: str,
        widget_chart_ids: list[str] | None = None,
        outline: list[dict] | None = None,
    ) -> str:
        css_block = _tokens_to_css_vars(tokens)
        css_wrapped = ":root {\n" + css_block + "}"
        chart_ids = widget_chart_ids or []
        widgets_section = _format_widgets_for_prompt(widgets, chart_ids)
        chart_instructions = ""
        if chart_ids:
            example_id = chart_ids[0]
            chart_instructions = (
                "\n\n## ⚡ CHART RENDERING — MANDATORY RULE\n"
                "The following widget IDs have been **pre-rendered as PNG chart images** by the "
                "backend and will be substituted into the deck after you return:\n\n"
                + "\n".join(f"  - `{wid}`" for wid in chart_ids)
                + "\n\n**For EACH of these widget IDs, you MUST emit an `<img>` tag with EXACTLY "
                + "this shape (no `src`, the backend fills it):**\n\n"
                + "```html\n"
                + f'<img class="widget-chart" data-osd-id="el-XXXX" data-widget-id="{example_id}" '
                + 'alt="チャートタイトル" style="width:100%; height:680px; object-fit:contain; display:block;" />\n'
                + "```\n\n"
                + "**REQUIREMENTS:**\n"
                + "- The `data-widget-id` value MUST be an EXACT MATCH from the list above.\n"
                + "- Set `data-osd-id` to a unique editable id like `s2-chart` or `el-XXXX`.\n"
                + "- DO NOT set `src` — the backend injects the rendered chart PNG.\n"
                + "- For widgets in the dashboard list that are NOT in the CHART READY list above, "
                + "skip them or use descriptive text only — DO NOT emit `<img data-widget-id>` for them.\n"
                + "- Aim for ONE chart per slide. Surrounding layout (caption, title, page number) "
                + "should leave room for a 1664×680ish chart area.\n"
                + "- Cover all CHART READY widgets across the deck — that's the whole point.\n"
            )
        task_chart_clause = ""
        if chart_ids:
            joined = ", ".join(f'"{w}"' for w in chart_ids)
            task_chart_clause = (
                f"\n\n**CHART CONTRACT (non-negotiable):** The backend has pre-rendered PNG charts "
                f"for these widget IDs: [{joined}]. For each one, embed exactly:\n"
                f'`<img class="widget-chart" data-osd-id="el-XXXX" data-widget-id="<ID>" alt="..." style="width:100%;height:680px;object-fit:contain;display:block;" />` '
                f'with the matching widget ID. **Every <img class="widget-chart"> tag MUST have a '
                f"data-widget-id attribute matching one of those IDs verbatim** — without that attribute "
                f"the chart cannot render and the deck is broken. Do NOT set src; the backend fills it. "
                f"Use one chart per slide; cover all listed widgets across the deck."
            )
        outline_block = ""
        if outline:
            lines: list[str] = []
            for i, entry in enumerate(outline, start=1):
                layout = entry.get("layout", "")
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                notes = entry.get("notes") or ""
                note_suffix = f" Notes: {notes}" if notes else ""
                lines.append(
                    f'{i}. [layout={layout}] "{title}" — Summary: {summary}{note_suffix}'
                )
            joined = "\n".join(lines)
            outline_block = (
                "## Required outline (must follow exactly)\n"
                'You MUST produce one <section class="slide" data-layout="..."> per outline entry, '
                "in the order given, with the specified layout and title. The summary tells you "
                "what content goes IN that slide. Follow the order strictly.\n\n"
                "Outline:\n"
                f"{joined}\n\n"
            )
        return (
            SLIDE_AUTHORING_RULES
            + "\n\n"
            + outline_block
            + "## Design tokens (use as CSS variables on :root or a slide wrapper)\n\n```css\n"
            + css_wrapped
            + "\n```\n\n## Theme narrative\n"
            + theme_markdown
            + "\n\n## Dashboard widgets (for data-aware copy)\n"
            + widgets_section
            + chart_instructions
            + "\n\n## User request\n"
            + user_prompt
            + "\n\n## Fidelity rules (HARD CONSTRAINTS — do not violate)\n\n"
            + "These rules trump any other guidance. Violations are silent failures users notice immediately.\n\n"
            + '**Title & deck-level naming.** Slide titles, the deck title, and every eyebrow / label MUST be derived from the supplied widget titles, column names, and dashboard name. Do not invent metric names that are not present in the metadata. Examples of phrases you must NEVER write unless they appear literally in widget titles or columns: "workload volume", "platform health", "sender reputation", "data platform performance", "quarter-over-quarter growth" — these are generic QBR clichés. Use the actual subject of the dashboard.\n\n'
            + "**Numeric content.** On `big-number`, `stat-row`, `callout`, and any other layout with numeric slots:\n"
            + "- If a widget has a `query_result_summary` field, you MAY quote a number from it verbatim — but never paraphrase into a different number or rounding.\n"
            + '- Without `query_result_summary`, do NOT invent a numeric value. Instead, render the slot as the column/expression name in monospaced caps (e.g., `DELIVERY_RATE`, `OPENS_RATE`), or write "—" if there is no defensible literal.\n'
            + "- Percentage signs, deltas (+X%), and currency symbols on fabricated values are forbidden.\n\n"
            + "**Numeric traceability.** Any element quoting a number from a widget MUST include "
            + 'data-source-widget-id="<widget_id>" on the element (or its closest ancestor). '
            + "This enables traceability between slide text and SQL data.\n\n"
            + '**Widget citation.** Every reference to widget data in slide markup MUST include the widget id in `<div class="stat-id">` or a similar visible citation slot, using the literal format `<widget-id> · <expression>` where `<expression>` is taken from that widget\'s `columns` list or `title`. Do not fabricate expression names.\n\n'
            + '**No generic QBR template.** Frame slides around the actual dashboard subject. If the dashboard is about marketing campaigns, the deck title and section headings must reflect marketing-campaign vocabulary, not "Data Platform Review".\n\n'
            + "## TASK\n"
            + "Produce a **complete HTML document** (DOCTYPE, `<html>`, `<head>`, `<body>`) for the slide deck. "
            + "Apply the theme using the CSS variables above. Each slide MUST be a `<section>` (or equivalent) "
            + "suitable for a 1920×1080 canvas. Every editable text or interactive region MUST include "
            + "`data-osd-id`. Return only the HTML, no surrounding explanation."
            + task_chart_clause
        )

    def _build_rewrite_element_prompt(
        self,
        *,
        target_outer_html: str,
        slide_excerpt: str,
        tokens: dict,
        theme_markdown: str,
        note: str,
    ) -> str:
        css_block = _tokens_to_css_vars(tokens)
        css_wrapped = ":root {\n" + css_block + "}"
        return (
            SLIDE_AUTHORING_RULES
            + "\n\n## Design tokens\n\n```css\n"
            + css_wrapped
            + "\n```\n\n## Theme narrative\n"
            + theme_markdown
            + "\n\n## Slide excerpt (context)\n"
            + slide_excerpt
            + "\n\n## Target element to replace (includes osd-comment marker)\n"
            + target_outer_html
            + "\n\n## Author note\n"
            + note
            + "\n\n## TASK\n"
            + "Return **one replacement** as a **single HTML element** (one root node) that will replace the "
            + "target. Preserve `data-osd-id` and remove or reconcile `osd-comment` markers as appropriate. "
            + "Output only that element's outer HTML, no markdown fences or explanation.\n\n"
            + "## Chart-data integrity (CRITICAL)\n"
            + 'If the target — or any descendant — is an `<img class="widget-chart" ...>` whose `src` '
            + "starts with `data:image/png;base64,`, that PNG is rendered server-side from REAL warehouse "
            + "data via the Vega-Lite pipeline. You have NO access to the underlying spec or rows. "
            + "Therefore:\n"
            + "- **NEVER replace, remove, or rewrap** that `<img>` with a hand-coded `<svg>`, `<canvas>`, "
            + "or HTML chart. Doing so fabricates data and is a correctness bug.\n"
            + "- **Preserve the `<img>` tag verbatim** (same `src`, `data-widget-id`, `data-osd-id`, "
            + "class, style). Copy it character-for-character into your output.\n"
            + "- You MAY edit anything around the chart: the slide eyebrow, slide title, the chart card "
            + "heading, the description / caption, the surrounding container layout, decorative chrome.\n"
            + "- If the note literally asks to change chart data, axes, colors, or marks "
            + "(e.g. 'use blue instead of red', 'only show top 3'), preserve the chart unchanged and "
            + "explain the limitation in the surrounding caption text instead (e.g. add a short "
            + "annotation below the chart in the slide language).\n"
            + "- **The `src` attribute may arrive empty** on widget-chart imgs — the deployment "
            + "pipeline strips the base64 PNG before calling you to stay under the input token "
            + "limit. Do NOT try to recreate or guess a src; just keep the `<img>` tag's other "
            + "attributes. The backend re-attaches the original src after your response.\n"
            + "\n## Semantic alignment for chart titles / eyebrows\n"
            + "If the note asks to rename a chart card's title or eyebrow, the new label MUST "
            + "describe what that specific chart actually plots. Each widget-chart img has an "
            + "`alt` attribute and a `data-widget-id` describing its data; the surrounding "
            + "card-id / caption usually carries the column expression. Pick the title that "
            + "matches the chart whose `alt` / `data-widget-id` corresponds to the user's "
            + "intent. If multiple cards exist and the note is ambiguous, prefer the FIRST "
            + "chart card in document order rather than guessing across them — do not rename "
            + "an unrelated chart."
        )

    def _build_add_slide_prompt(
        self,
        *,
        deck_html: str,
        tokens: dict,
        theme_markdown: str,
        user_prompt: str,
    ) -> str:
        css_block = _tokens_to_css_vars(tokens)
        css_wrapped = ":root {\n" + css_block + "}"
        return (
            SLIDE_AUTHORING_RULES
            + "\n\n## Design tokens\n\n```css\n"
            + css_wrapped
            + "\n```\n\n## Theme narrative\n"
            + theme_markdown
            + "\n\n## Existing deck HTML (append one new slide)\n"
            + deck_html
            + "\n\n## User request\n"
            + user_prompt
            + "\n\n## TASK\n"
            + "Output **one new slide** as a single `<section>` root element. The section MUST include a unique "
            + "`data-slide-id` attribute. Every editable element inside MUST include `data-osd-id`. "
            + "Do not repeat the full document—only the new `<section>...</section>` fragment. "
            + "Match the deck's visual language using the tokens above."
        )

    def _build_html_to_spec_prompt(self, *, deck_html: str) -> str:
        return (
            "You convert an HTML slide deck into a JSON slide specification.\n\n"
            + AVAILABLE_LAYOUTS
            + "\n\n## HTML deck\n"
            + deck_html
            + "\n\n**For closing slides specifically**: extract the slide's heading text into `title` "
            + 'and the body sentence (the line that says "thank you" / "questions" / etc.) '
            + "into `subtitle`. Do NOT leave closing slides with empty content — "
            + "they should display the heading and body just like any other slide.\n\n"
            + "## TASK\n"
            + "Analyze the slides and emit **only** a JSON array in **create-from-spec** format "
            + "(same contract as layout keys above). Map each logical slide to the closest layout; "
            + "preserve titles and body text. No markdown fences—raw JSON array only."
        )

    def _parse_response(self, raw: str) -> list[dict[str, Any]]:
        """Extract a JSON array from markdown-fenced or raw model output."""
        text = raw
        match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
        text = text.strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Failed to parse LLM response as JSON: {exc}\nRaw: {text[:500]}"
            ) from exc
        if not isinstance(parsed, list):
            raise ValueError("LLM response is not a JSON array")
        return parsed

    @staticmethod
    def _design_uses_available_fields(
        design: ChartDesign, available_fields: list[str]
    ) -> bool:
        allowed = set(available_fields)
        for field_name in (
            design.category_field,
            design.value_field,
            design.series_field,
        ):
            if field_name is not None and field_name not in allowed:
                return False
        return True

    @staticmethod
    def _clamp_design_top_n(raw_design: dict[str, Any]) -> dict[str, Any]:
        design_dict = dict(raw_design)
        top_n = design_dict.get("top_n")
        if top_n is None:
            return design_dict
        try:
            top_n_int = int(top_n)
        except (TypeError, ValueError):
            design_dict.pop("top_n", None)
            return design_dict
        if top_n_int < 1:
            design_dict.pop("top_n", None)
        elif top_n_int > 20:
            design_dict["top_n"] = 20
        else:
            design_dict["top_n"] = top_n_int
        return design_dict

    def _parse_chart_design_from_raw(
        self,
        raw_design: Any,
        available_fields: list[str],
    ) -> ChartDesign | None:
        from pydantic import ValidationError

        if not isinstance(raw_design, dict):
            return None
        try:
            clamped = self._clamp_design_top_n(raw_design)
            design = ChartDesign.model_validate(clamped)
            if not self._design_uses_available_fields(design, available_fields):
                return None
            return design
        except ValidationError:
            return None

    def augment_chart_specs_for_deck(
        self,
        *,
        widgets_with_data: list[dict],
        slide_outline: list[dict],
        tokens: dict,
    ) -> list[ChartAugmentation]:
        """Single LLM call producing structured chart augmentations per widget_id.

        Returns an empty list on transport errors or invalid JSON. Widget entries
        that fail schema validation are omitted without failing the batch.
        """
        import sys

        from pydantic import ValidationError

        if not self._client:
            return []

        system_msg = (
            "You are a presentation designer improving dashboard charts for slide decks.\n"
            "Each widget includes `available_fields` (the exact column keys in `rows_sample`).\n"
            "\n"
            "## Step 1 — Design the chart (analytical intent)\n"
            "FIRST choose a `design` object from the question's intent, then add decoration.\n"
            "Set `design` to null when the heuristic chart is fine and you only need decoration.\n"
            "\n"
            "Intent → design rules:\n"
            '- Ranking / top / most / least → chart_type "bar", sort "value_desc", '
            'set top_n (8–15). Prefer orientation "horizontal" when category labels are '
            "long text (emails, names, event types).\n"
            '- Trend over time → chart_type "line" (do NOT set top_n or sort).\n'
            '- Part-of-whole / share → chart_type "pie" sparingly (≤ 6 slices).\n'
            '- Correlation → chart_type "scatter".\n'
            "- category_field, value_field, and series_field MUST each be one of "
            "`available_fields` when set.\n"
            "\n"
            "## Step 2 — Decoration (optional story layer)\n"
            "Pick AT MOST ONE concise story when the data clearly supports it; otherwise leave\n"
            "every optional field null / empty (a plain chart is better than a wrong story).\n"
            "\n"
            "## Hard rules\n"
            "- `highlight.field` MUST be one of `available_fields` for that widget. "
            "If you cannot identify which field to highlight, set `highlight` to null.\n"
            "- `highlight.values` MUST be drawn from values actually present in `rows_sample` "
            "for that field (copy them verbatim — do not paraphrase or translate).\n"
            "- When you set design.top_n, every `highlight.values` entry MUST be a category "
            "that survives the designed top_n ranking (do not highlight a category top_n drops).\n"
            "- `reference_line.value` must fall within the data extent of that axis.\n"
            "- `y_range` only when zooming in genuinely clarifies the story; range must lie "
            "inside the data extent.\n"
            "- At most one reference_line per widget.\n"
            '- `value_format` ONLY one of: "currency" | "percent" | "count" | "duration". '
            "Pick currency when y aggregates revenue/spend; percent when y is a ratio in [0,1]; "
            "count for integer counts; duration for time-in-units; else null.\n"
            "- `caption` ≤ 80 chars, in the deck's primary language (mirror tokens.language or "
            "the slide outline language).\n"
            "\n"
            "## Output\n"
            "STRICT JSON only — no markdown fences, no commentary, no trailing text.\n"
            'Schema: {"augmentations":[{"widget_id":"...", '
            '"design":{"chart_type":"bar"|"line"|"area"|"pie"|"scatter"|null,'
            '"category_field":"..."|null,"value_field":"..."|null,'
            '"series_field":"..."|null,'
            '"aggregate":"sum"|"avg"|"count"|"none",'
            '"sort":"value_desc"|"value_asc"|"category"|"none",'
            '"top_n":int|null,"orientation":"horizontal"|"vertical"|null}|null, '
            '"highlight":{"field":"...","values":["..."]}|null, '
            '"y_range":[min,max]|null, '
            '"reference_line":{"axis":"y"|"x","value":number,"label":"..."}|null, '
            '"value_format":"currency"|"percent"|"count"|"duration"|null, '
            '"caption":"<=80 chars"|null}]}\n'
            "\n"
            "## Example (one widget in, one augmentation out)\n"
            "Input widget:\n"
            '  {"widget_id":"w1","title":"年代別平均購入額",'
            '"available_fields":["age_band","avg_spend"],'
            '"rows_sample":[{"age_band":"20代","avg_spend":1200},'
            '{"age_band":"30代","avg_spend":1900},{"age_band":"40代","avg_spend":2400},'
            '{"age_band":"50代","avg_spend":3100},{"age_band":"60代以上","avg_spend":2200}]}\n'
            "Good output:\n"
            '  {"widget_id":"w1",'
            '"design":{"chart_type":"bar","category_field":"age_band",'
            '"value_field":"avg_spend","series_field":null,'
            '"aggregate":"none","sort":"value_desc","top_n":5,'
            '"orientation":"horizontal"},'
            '"highlight":{"field":"age_band","values":["50代"]},'
            '"y_range":null,'
            '"reference_line":{"axis":"y","value":2160,"label":"平均"},'
            '"value_format":"currency","caption":"50代が突出して高単価"}\n'
            'Note: `highlight.field` is "age_band" (an available_field); the highlighted value '
            'is "50代" copied verbatim from rows_sample and kept within top_n categories.'
        )

        payload = json.dumps(
            {
                "slide_outline": slide_outline or [],
                "widgets": widgets_with_data or [],
                "tokens": tokens or {},
            },
            default=str,
        )
        user_msg = (
            "Analyze each widget's sampled rows and the slide outline; emit augmentations.\n\n"
            f"{payload}"
        )

        try:
            raw_text = self._foundation_model_chat_sync(
                [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=4096,
                temperature=0.2,
                timeout_s=180.0,
                endpoint=self._edit_endpoint,
            )
        except Exception as exc:
            print(
                f"[chart-augment] LLM transport error: {exc}",
                file=sys.stderr,
                flush=True,
            )
            return []

        text = (raw_text or "").strip()
        fenced = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if fenced:
            text = fenced.group(1).strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            print("[chart-augment] non-JSON", file=sys.stderr, flush=True)
            return []

        raw_items = parsed.get("augmentations") if isinstance(parsed, dict) else None
        if not isinstance(raw_items, list):
            return []

        fields_by_widget: dict[str, list[str]] = {}
        for widget in widgets_with_data or []:
            if not isinstance(widget, dict):
                continue
            widget_id = widget.get("widget_id")
            available_fields = widget.get("available_fields")
            if isinstance(widget_id, str) and isinstance(available_fields, list):
                fields_by_widget[widget_id] = [
                    field for field in available_fields if isinstance(field, str)
                ]

        results: list[ChartAugmentation] = []
        for raw_entry in raw_items:
            if not isinstance(raw_entry, dict):
                continue
            entry = dict(raw_entry)
            raw_design = entry.pop("design", None)
            try:
                aug = ChartAugmentation.model_validate(entry)
            except ValidationError as exc:
                print(
                    f"[chart-augment] widget validation skipped: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
                continue
            available_fields = fields_by_widget.get(aug.widget_id, [])
            design = self._parse_chart_design_from_raw(raw_design, available_fields)
            results.append(aug.model_copy(update={"design": design}))
        return results
