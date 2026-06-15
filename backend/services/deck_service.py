"""Deck orchestration: generate / save-comment / apply-comment / add-slide / delete-slide.

Validation is deck-wide (uniqueness of data-osd-id and data-slide-id, slide-root
preservation on element rewrites). On any validation failure, no DB writes occur.

UC SQL has no transactions; we sequence writes carefully and rely on
update_deck_html being a single statement.
"""

from __future__ import annotations

import json
import re
import secrets
from copy import copy
import warnings
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from models import Deck, DeckRevision, PendingComment, WidgetInfo
from services.brand_styles import get_brand_css, inject_brand_css
from services.marker_service import (
    OSD_COMMENT_RE,
    find_marker,
    generate_element_id,
    insert_marker,
    list_markers,
    remove_marker,
)
from services.pptx_import_service import (
    build_html_from_extracted,
    extract_slides_from_pptx,
)
from services.sanitizer_service import sanitize_deck_html


_MAX_REVISIONS = 20

_KNOWN_LAYOUTS = {
    "title",
    "section",
    "closing",
    "content",
    "one-column",
    "two-column",
    "two-column-icons",
    "three-column",
    "three-column-icons",
    "comparison",
    "pros-cons",
    "cards",
    "card-left",
    "card-right",
    "card-full",
    "big-number",
    "stat-row",
    "agenda",
    "timeline",
    "icon-grid",
    "checklist",
    "quote",
    "callout",
    "logos",
    "section-description",
}

_FENCE_WRAP_RE = re.compile(r"^```(?:html|HTML)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)
_FENCE_ANY_RE = re.compile(r"```(?:html|HTML|json|JSON)?\s*", re.IGNORECASE)


def _strip_markdown_fence(text: str) -> str:
    """Remove markdown code fences from LLM output.

    LLMs (Claude in particular) wrap HTML responses in ```html ... ``` and
    sometimes drop nested fences inside the body. Strip any ``` markers
    anywhere in the text — they should never appear in valid HTML output.
    """
    if not text:
        return text
    s = text.strip()
    m = _FENCE_WRAP_RE.match(s)
    if m:
        s = m.group(1).strip()
    s = _FENCE_ANY_RE.sub("", s)
    s = s.replace("```", "")
    return s.strip()


_HARDCODED_WHITE_RE = re.compile(
    r"color\s*:\s*(#fff(?:fff)?|white|rgba?\(\s*255\s*,\s*255\s*,\s*255\s*[^)]*\))",
    re.IGNORECASE,
)
_HARDCODED_BLACK_RE = re.compile(
    r"color\s*:\s*(#000(?:000)?|black|rgba?\(\s*0\s*,\s*0\s*,\s*0\s*[^)]*\))",
    re.IGNORECASE,
)
_BODY_BG_RE = re.compile(
    r"(body\s*\{[^}]*?background(?:-color)?\s*:\s*)([^;}]+)([;}])", re.IGNORECASE
)


def _normalize_deck_css(html: str) -> str:
    """Force the deck's CSS to honor design tokens.

    LLMs frequently hardcode `color: #ffffff` for cover/hero titles assuming a
    dark canvas, then forget to actually set a dark background — leaving white
    text on the canonical (light) bg. Replace literal white/black with token
    refs so the deck stays readable across light/dark presets.

    Also force `body { background }` to use --osd-bg so the canvas behind
    sections matches the preset.
    """
    soup = BeautifulSoup(html, "html.parser")
    for style in soup.find_all("style"):
        if not style.string:
            continue
        css = style.string
        css = _HARDCODED_WHITE_RE.sub("color: var(--osd-text)", css)
        css = _HARDCODED_BLACK_RE.sub("color: var(--osd-text)", css)
        css = _BODY_BG_RE.sub(r"\1var(--osd-bg)\3", css)
        style.string.replace_with(css)

    # Append demo-grade safety CSS for common cover layout patterns LLM emits.
    # title-meta is the cover's author/date/audience row — force flex-wrap so
    # narrow viewports don't truncate it.
    safety_css = (
        "\n.title-meta { display: flex; flex-wrap: wrap; gap: 16px 24px; }\n"
        ".title-meta-item { white-space: nowrap; }\n"
    )
    first_style = soup.find("style")
    if first_style is not None:
        existing = first_style.string or ""
        if ".title-meta" not in existing:
            first_style.string = existing + safety_css

    return str(soup)


_ACCENT_RE = re.compile(r"\*\*([^*\n]+?)\*\*")

_SKIP_ACCENT_ANCESTOR_TAGS = frozenset({"style", "script", "head", "title", "meta"})


def _text_node_in_skip_zone(text_node: NavigableString) -> bool:
    el = getattr(text_node, "parent", None)
    while el is not None:
        if getattr(el, "name", None) in _SKIP_ACCENT_ANCESTOR_TAGS:
            return True
        el = getattr(el, "parent", None)
    return False


def _normalize_accent_markers(html: str) -> str:
    """Convert **phrase** in text content to <span class="accent">phrase</span>.

    Adds .accent { color: var(--osd-accent) } to the first <style> block if absent.
    """
    soup = BeautifulSoup(html, "html.parser")

    for text_node in list(soup.find_all(string=True)):
        if not isinstance(text_node, NavigableString):
            continue
        if _text_node_in_skip_zone(text_node):
            continue
        original = str(text_node)
        if "**" not in original:
            continue
        if not _ACCENT_RE.search(original):
            continue
        new_parts = []
        last_end = 0
        for m in _ACCENT_RE.finditer(original):
            if m.start() > last_end:
                new_parts.append(NavigableString(original[last_end : m.start()]))
            span = soup.new_tag("span", attrs={"class": "accent"})
            span.string = m.group(1)
            new_parts.append(span)
            last_end = m.end()
        if last_end < len(original):
            new_parts.append(NavigableString(original[last_end:]))
        text_node.replace_with(*new_parts)

    first_style = soup.find("style")
    if first_style is not None:
        css = first_style.string or ""
        if ".accent" not in css:
            first_style.string = css + "\n.accent { color: var(--osd-accent); }\n"

    return str(soup)


_LLM_FOOTER_COPYRIGHT = "Databricks Inc. — All rights reserved"

_FOOTER_WRAPPER_CLASS_PREFIX_RE = re.compile(
    r"^(?:deck|slide|closing|cover|section|page|brand)[_-]?(?:foot|footer)$"
)


def _is_strip_llm_footer_wrapper(tag: Tag) -> bool:
    """True for direct-removable footer chrome wrappers (div/footer), by class token."""
    if tag.name not in ("div", "footer"):
        return False
    for cls in tag.get("class") or []:
        if cls.endswith("-foot") or cls.endswith("-footer"):
            return True
        if _FOOTER_WRAPPER_CLASS_PREFIX_RE.match(cls):
            return True
    return False


def _is_strip_llm_deck_logo_img(tag: Tag) -> bool:
    if tag.name != "img":
        return False
    classes = tag.get("class") or []
    if "deck-logo" in classes:
        return True
    src = (tag.get("src") or "").lower()
    return "databricks-logo" in src


def _is_strip_llm_footer_text_span(tag: Tag) -> bool:
    if tag.name == "span":
        classes = tag.get("class") or []
        if "footer-text" in classes:
            return True
    text = tag.get_text("", strip=True)
    if not text:
        return False
    lowered = text.lower()
    if lowered.startswith("databricks inc."):
        return tag.name in ("span", "p")
    if tag.name != "span":
        return False
    return text == _LLM_FOOTER_COPYRIGHT


def _is_strip_llm_page_number_span(tag: Tag) -> bool:
    if tag.name != "span":
        return False
    classes = tag.get("class") or []
    if "page-number" in classes:
        return True
    text = tag.get_text("", strip=True)
    return bool(text and text.isdigit())


def _strip_llm_footer_targets_under(tag: Tag) -> None:
    """Remove LLM footer markup among direct children of ``tag`` (mutates ``tag``)."""
    for child in list(tag.children):
        if not isinstance(child, Tag):
            continue
        if _is_strip_llm_footer_wrapper(child):
            child.decompose()
            continue
        if _is_strip_llm_deck_logo_img(child):
            child.decompose()
            continue
        if _is_strip_llm_footer_text_span(child) or _is_strip_llm_page_number_span(
            child
        ):
            child.decompose()


def _strip_llm_footer_triplet(html: str) -> str:
    """Drop LLM-emitted footer chrome; brand CSS supplies the copyright line instead.

    Only strips direct children of ``section.slide`` (including wrapper divs /
    footers whose classes look like slide footers, e.g. ``closing-foot``); nested
    hero content (cover logos inside inner divs) is not touched.
    """
    soup = _parse(html)
    for section in soup.find_all("section"):
        classes = section.get("class") or []
        if "slide" not in classes:
            continue
        _strip_llm_footer_targets_under(section)
    return str(soup)


_SHAPE_CSS_PROPS = (
    "clip-path",
    "background",
    "border",
    "mask",
    "transform",
    "border-image",
)
_SELECTOR_DECL_RE = re.compile(r"([^{]+)\{([^{}]*)\}")


def _strip_empty_decorative_divs(html: str) -> str:
    """Remove <div class="..."></div> elements that have no content AND
    whose classes don't appear in any <style> rule with a clip-path /
    background / border-image / mask declaration. These are LLM-emitted
    decorative shapes (e.g., accent triangles) without matching CSS,
    which render as gray boxes.
    """
    import sys

    soup = _parse(html)

    shape_classes: set[str] = set()
    for style in soup.find_all("style"):
        css = style.string or ""
        for m in _SELECTOR_DECL_RE.finditer(css):
            selector = m.group(1).strip()
            decl = m.group(2)
            if selector.lstrip().startswith("@"):
                continue
            if not any(p in decl for p in _SHAPE_CSS_PROPS):
                continue
            for cls_m in re.finditer(r"\.([\w-]+)\b", selector):
                shape_classes.add(cls_m.group(1))

    removed = 0
    for div in list(soup.find_all("div")):
        classes = div.get("class") or []
        if not classes:
            continue
        if div.get_text(strip=True):
            continue
        if any(
            getattr(c, "name", None) for c in div.children if getattr(c, "name", None)
        ):
            continue
        if any(cls in shape_classes for cls in classes):
            continue
        div.decompose()
        removed += 1

    if removed:
        print(
            f"[normalize] stripped {removed} empty decorative divs",
            file=sys.stderr,
            flush=True,
        )

    return str(soup)


def _has_data_image_src(img: Any) -> bool:
    return (img.get("src") or "").startswith("data:image/")


def _inject_widget_chart_srcs(html: str, widget_charts: dict[str, str]) -> str:
    """Inject chart data URIs into deck <img> tags.

    Two-stage match:
    1. For every <img>, if data-widget-id matches a key in widget_charts, set src.
       (LLMs sometimes omit the widget-chart class but keep data-widget-id.)
    2. For <img class="widget-chart"> still missing src, assign unused widget IDs
       in document order. LLMs frequently drop data-widget-id even when instructed,
       so the fallback keeps the demo working.
    """
    import sys

    print(
        f"[charts] _inject_widget_chart_srcs called with {len(widget_charts)} charts",
        file=sys.stderr,
        flush=True,
    )
    soup = BeautifulSoup(html, "html.parser")
    chart_imgs = soup.find_all("img", class_="widget-chart")
    print(
        f"[charts] found {len(soup.find_all('img'))} imgs total, {len(chart_imgs)} with widget-chart class",
        file=sys.stderr,
        flush=True,
    )
    consumed: set[str] = set()
    for img in soup.find_all("img"):
        wid = img.get("data-widget-id")
        if wid and wid in widget_charts:
            img["src"] = widget_charts[wid]
            consumed.add(wid)

    fallback_iter = iter(w for w in widget_charts if w not in consumed)
    for img in chart_imgs:
        if img.get("src"):
            continue
        try:
            wid = next(fallback_iter)
        except StopIteration:
            break
        img["data-widget-id"] = wid
        img["src"] = widget_charts[wid]
    return str(soup)


_EYEBROW_OR_SUBTITLE_CLS = re.compile(r"eyebrow|kicker|subtitle", re.I)


def _has_emoji(s: str) -> bool:
    """Return True if string contains a character in common emoji / symbol ranges."""
    return any(0x2600 <= ord(c) <= 0x27BF or 0x1F000 <= ord(c) <= 0x1FFFF for c in s)


def _infer_layout_from_content(section: Tag, position: str = "middle") -> str:
    """Best-effort heuristic to pick a layout name from a section's structure.

    `position` is "first", "last", or "middle" depending on the section's index
    in the deck.
    """
    text = section.get_text(" ", strip=True)
    text_len = len(text)

    checkmarks = sum(text.count(c) for c in ("✓", "☑"))
    crosses = sum(text.count(c) for c in ("✗", "☒"))
    open_circles = sum(text.count(c) for c in ("○", "☐"))
    has_blockquote = bool(section.find("blockquote"))

    h1s = section.find_all("h1")
    h2s = section.find_all("h2")
    headings = section.find_all(["h1", "h2", "h3"])

    has_eyebrow = bool(section.find(class_=_EYEBROW_OR_SUBTITLE_CLS))
    has_subtitle_block = bool(section.find("p")) or bool(
        section.find(class_=re.compile(r"subtitle", re.I))
    )

    bare_digits = section.find_all(string=re.compile(r"^\s*\d+\s*$"))
    digit_clusters = re.findall(r"\b\d+(?:\.\d+)?[%xKMB$]?\b", text)

    # 1. Title (first slide, h1 + context, sparse)
    if (
        position == "first"
        and h1s
        and (has_eyebrow or has_subtitle_block)
        and text_len < 600
    ):
        return "title"

    # 2. Section divider (large 2-digit number + minimal content)
    if (
        text_len < 400
        and (h1s or h2s)
        and re.search(r"\b(?:0[1-9]|[12][0-9]|30)\b", text)
    ):
        return "section"

    # 3. Closing (last slide, thank-you or very sparse)
    if position == "last" and (
        "thank" in text.lower() or (text_len < 200 and len(h1s) <= 1 and not h2s)
    ):
        return "closing"

    # 4. Quote (blockquote OR opens with curly-quote)
    if has_blockquote or text.lstrip().startswith(("“", "「", '"')):
        return "quote"

    # 5. Pros-cons (both ✓ and ✗)
    if checkmarks >= 2 and crosses >= 2:
        return "pros-cons"

    # 6. Checklist (✓ + ○ pattern, no ✗)
    if (checkmarks + open_circles) >= 3 and crosses == 0:
        return "checklist"

    # 7. Big-number — find a single huge stat in a text node
    big_num = section.find(string=re.compile(r"^\s*[+-]?\$?\d+(?:\.\d+)?[%xKMB$]?\s*$"))
    if big_num and text_len < 300:
        return "big-number"

    # 8. Agenda — bare digit markers 1, 2, 3, 4... (before stat-row; avoids 1/2/3 → stat-row)
    if len(bare_digits) >= 4:
        return "agenda"

    # 9. Timeline — exactly 3 bare-digit bullets + section heading
    if len(bare_digits) == 3 and h2s:
        return "timeline"

    # 10. Stat-row — several numeric tokens in short copy (not bare 1/2/3 step markers)
    if len(digit_clusters) >= 3 and text_len < 400 and len(bare_digits) < 3:
        return "stat-row"

    # 11. Callout — short statement, at most one heading, no lists
    if (
        text_len < 220
        and len(headings) <= 1
        and not section.find(["ul", "ol"])
        and len(bare_digits) < 3
    ):
        return "callout"

    # 12. Icon-grid — 3+ items with leading emoji
    icon_items = [
        n
        for n in section.find_all(["div", "li", "span"])
        if _has_emoji((n.get_text("", strip=True) or "")[:2])
    ]
    if len(icon_items) >= 3:
        return "icon-grid"

    # 13. Three-column-icons / three-column / two-column based on column count
    column_candidates = section.find_all(class_=re.compile(r"\bcol(?:umn)?s?\b", re.I))
    if len(column_candidates) == 3:
        if any(
            _has_emoji((c.get_text("", strip=True) or "")[:2])
            for c in column_candidates
        ):
            return "three-column-icons"
        return "three-column"
    if len(column_candidates) == 2:
        return "two-column"

    return "content"


def _normalize_slide_sections(html: str) -> str:
    """Ensure every section that looks like a slide has class="slide" + data-slide-id + data-osd-id.

    LLM output varies — sometimes `<section id="slide-1">` without class, sometimes class but
    no data-slide-id. Walk top-level <section> children of <body> and stamp the required attrs.
    """
    soup = BeautifulSoup(html, "html.parser")
    body = soup.find("body") or soup
    # Top-level body sections are assumed to be slides (they get class="slide" added).
    # Plus any other <section class="slide"> elsewhere in the doc gets normalized too,
    # to be defensive against LLM output with nested or wrapped slide sections.
    top_level = [c for c in body.children if getattr(c, "name", None) == "section"]
    seen_ids = {id(s) for s in top_level}
    nested_slides = [
        s
        for s in soup.find_all("section")
        if id(s) not in seen_ids and "slide" in (s.get("class") or [])
    ]
    sections = top_level + nested_slides
    used_slide_ids: set[str] = set()
    used_osd_ids: set[str] = set()
    for el in soup.find_all(attrs={"data-osd-id": True}):
        used_osd_ids.add(el.get("data-osd-id", ""))
    for el in soup.find_all(attrs={"data-slide-id": True}):
        used_slide_ids.add(el.get("data-slide-id", ""))

    for i, section in enumerate(sections, start=1):
        classes = section.get("class") or []
        if "slide" not in classes:
            classes = list(classes) + ["slide"]
            section["class"] = classes
        slide_id = section.get("data-slide-id")
        if not slide_id:
            slide_id = f"s{i}"
            while slide_id in used_slide_ids:
                slide_id = f"s{i}-{secrets.token_hex(2)}"
            section["data-slide-id"] = slide_id
            used_slide_ids.add(slide_id)
        osd_id = section.get("data-osd-id")
        if not osd_id:
            osd_id = f"el-{secrets.token_hex(3)}"
            while osd_id in used_osd_ids:
                osd_id = f"el-{secrets.token_hex(3)}"
            section["data-osd-id"] = osd_id
            used_osd_ids.add(osd_id)

        # data-layout: infer from class names; if missing, use structure heuristics (fallback content).
        classes = section.get("class") or []
        if not section.get("data-layout"):
            inferred = None
            for cls in classes:
                if cls in _KNOWN_LAYOUTS:
                    inferred = cls
                    break
            if not inferred:
                if i == 1:
                    pos = "first"
                elif i == len(sections):
                    pos = "last"
                else:
                    pos = "middle"
                inferred = _infer_layout_from_content(section, position=pos)
            section["data-layout"] = inferred
    return str(soup)


class DeckValidationError(Exception):
    pass


class DeckRepo(Protocol):
    def insert_deck(self, deck: Deck) -> None: ...
    def get_deck(self, deck_id: str, user_id: str) -> Deck | None: ...
    def list_decks(self, user_id: str) -> list[Deck]: ...
    def update_deck_html(self, deck_id: str, html_doc: str) -> None: ...
    def update_deck_gslides_link(
        self, deck_id: str, user_id: str, file_id: str, url: str
    ) -> None: ...
    def insert_revision(self, rev: DeckRevision) -> None: ...
    def count_revisions(self, deck_id: str) -> int: ...
    def delete_oldest_non_genesis_revision(self, deck_id: str) -> None: ...
    def delete_deck(self, deck_id: str, user_id: str) -> None: ...


def _parse(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "html.parser")
    except Exception as e:  # pragma: no cover
        raise DeckValidationError(f"unparseable html: {e}") from e


def _all_osd_ids(soup: BeautifulSoup) -> list[str]:
    return [
        el.get("data-osd-id", "") for el in soup.find_all(attrs={"data-osd-id": True})
    ]


def _all_slide_ids(soup: BeautifulSoup) -> list[str]:
    return [
        el.get("data-slide-id", "")
        for el in soup.find_all("section", attrs={"class": True, "data-slide-id": True})
        if "slide" in (el.get("class") or [])
    ]


def _validate_deck_invariants(html: str) -> None:
    soup = _parse(html)
    ids = _all_osd_ids(soup)
    if len(ids) != len(set(ids)):
        dups = [x for x in set(ids) if ids.count(x) > 1 and x]
        raise DeckValidationError(f"duplicate data-osd-id: {dups}")
    sids = _all_slide_ids(soup)
    if len(sids) != len(set(sids)):
        dup_s = {s for s in sids if s and sids.count(s) > 1}
        raise DeckValidationError(f"duplicate data-slide-id: {dup_s}")
    for section in soup.find_all("section"):
        classes = section.get("class") or []
        if "slide" not in classes:
            continue
        if not section.get("data-slide-id"):
            raise DeckValidationError("slide <section> missing data-slide-id")
        if not section.get("data-osd-id"):
            raise DeckValidationError("slide <section> missing data-osd-id")

    for section in soup.find_all("section"):
        classes = section.get("class") or []
        if "slide" not in classes:
            continue
        layout = section.get("data-layout")
        if layout and layout not in _KNOWN_LAYOUTS:
            warnings.warn(
                f"unknown data-layout='{layout}' on slide "
                f"{section.get('data-slide-id', '?')} (will render but "
                f"won't match any known scaffold)",
                stacklevel=2,
            )


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass
class _SlideRootInfo:
    is_slide_root: bool
    data_slide_id: str | None
    classes: list[str]


def _slide_root_info(soup: BeautifulSoup, target_id: str) -> _SlideRootInfo:
    el = soup.find(attrs={"data-osd-id": target_id})
    if el is None or el.name != "section":
        return _SlideRootInfo(False, None, [])
    classes = el.get("class") or []
    if "slide" not in classes:
        return _SlideRootInfo(False, None, [])
    return _SlideRootInfo(True, el.get("data-slide-id"), classes)


class DeckService:
    def __init__(self, *, llm: Any, repo: DeckRepo) -> None:
        self._llm = llm
        self._repo = repo

    def get_deck(self, deck_id: str, user_id: str) -> Deck | None:
        return self._repo.get_deck(deck_id, user_id)

    def list_decks(self, user_id: str) -> list[Deck]:
        return self._repo.list_decks(user_id)

    def update_gslides_link(
        self, deck_id: str, user_id: str, file_id: str, url: str
    ) -> None:
        """Persist last Google Slides export id/url for in-place re-export."""
        self._require_deck(deck_id, user_id)
        self._repo.update_deck_gslides_link(deck_id, user_id, file_id, url)

    def generate_outline(
        self,
        *,
        tokens: dict[str, Any],
        theme_markdown: str,
        widgets: list[WidgetInfo],
        user_prompt: str | None,
        reference_doc: str | None = None,
        reference_doc_name: str | None = None,
    ) -> list[dict]:
        """Return parsed outline slides. Raises DeckValidationError on bad JSON."""
        raw = self._llm.generate_deck_outline(
            tokens=tokens,
            theme_markdown=theme_markdown,
            widgets=widgets,
            user_prompt=user_prompt or "",
            reference_doc=reference_doc,
            reference_doc_name=reference_doc_name,
        )
        cleaned = _strip_markdown_fence(raw)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise DeckValidationError(f"outline JSON parse failed: {e}") from e
        slides = data.get("slides") if isinstance(data, dict) else None
        if not isinstance(slides, list) or not slides:
            raise DeckValidationError("outline must contain non-empty 'slides' list")
        out: list[dict] = []
        for s in slides[:20]:
            if not isinstance(s, dict):
                continue
            out.append(
                {
                    "layout": str(s.get("layout") or "content"),
                    "title": str(s.get("title") or "")[:120],
                    "summary": str(s.get("summary") or "")[:300],
                    "notes": str(s.get("notes") or "")[:500],
                }
            )
        if not out:
            raise DeckValidationError("outline produced no valid slides")
        return out

    def _reconcile_layouts_with_outline(
        self,
        html: str,
        outline: list[dict],
        *,
        tokens: dict[str, Any],
        theme_markdown: str,
    ) -> str:
        soup = BeautifulSoup(html, "html.parser")
        sections = [
            s for s in soup.find_all("section") if "slide" in (s.get("class") or [])
        ]
        if len(sections) != len(outline):
            return html
        changed = False
        for entry, section in zip(outline, sections):
            want = str(entry.get("layout") or "").strip()
            got_raw = section.get("data-layout")
            got = str(got_raw).strip() if got_raw else ""
            if not want or want == got:
                continue
            outline_title = str(entry.get("title", "") or "")
            outline_summary = str(entry.get("summary", "") or "")
            slide_id = str(section.get("data-slide-id", "") or "")
            osd_id = str(section.get("data-osd-id", "") or "")
            feedback = (
                f'This slide MUST have data-layout="{want}" per the outline. '
                f'Outline: layout={want}, title="{outline_title}", '
                f'summary="{outline_summary}". '
                f"Rewrite to match that layout shape exactly. "
                f'Preserve the existing data-slide-id="{slide_id}" '
                f'and data-osd-id="{osd_id}" attributes. '
                f"Use the same CSS classes as the rest of the deck (deck-footer, deck-logo, "
                f"slide-topbar, eyebrow, accent, etc.)."
            )
            new_section_html = self._llm.regenerate_slide_section(
                deck_html=str(soup),
                slide_outer_html=str(section),
                tokens=tokens,
                theme_markdown=theme_markdown,
                feedback=feedback,
            )
            new_soup = BeautifulSoup(
                _strip_markdown_fence(new_section_html), "html.parser"
            )
            new_section = new_soup.find("section")
            if new_section is not None:
                section.replace_with(new_section)
                changed = True
        return str(soup) if changed else html

    def audit_deck(self, *, deck_id: str, user_id: str) -> list[dict]:
        """Run a design audit on the deck. Returns list of issue dicts."""
        deck = self._require_deck(deck_id, user_id)
        raw = self._llm.audit_deck(
            deck_html=deck.html_doc,
            tokens=deck.design_tokens,
            theme_markdown=deck.theme_markdown,
        )
        cleaned = _strip_markdown_fence(raw)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return []
        issues = data.get("issues") if isinstance(data, dict) else None
        if not isinstance(issues, list):
            return []
        out = []
        for x in issues[:20]:
            if not isinstance(x, dict):
                continue
            out.append(
                {
                    "slide_id": str(x.get("slide_id") or ""),
                    "severity": str(x.get("severity") or "P2")[:4],
                    "message": str(x.get("message") or "")[:300],
                    "fix_hint": str(x.get("fix_hint") or "")[:300],
                }
            )
        return out

    def audit_and_fix_deck(
        self, *, deck_id: str, user_id: str
    ) -> tuple[Deck, list[dict]]:
        """High-quality mode: audit, then regenerate slides flagged P0/P1.

        Returns the (possibly improved) deck + the original issues list.
        """
        issues = self.audit_deck(deck_id=deck_id, user_id=user_id)
        fixable: dict[str, list[dict]] = {}
        for iss in issues:
            if iss["severity"] in ("P0", "P1") and iss["slide_id"]:
                sid = iss["slide_id"]
                fixable.setdefault(sid, []).append(iss)

        deck = self._require_deck(deck_id, user_id)
        for sid, slide_issues in fixable.items():
            feedback = " | ".join(
                f"{i['message']} (fix: {i['fix_hint']})" for i in slide_issues
            )
            try:
                deck, _ = self.regenerate_slide(
                    deck_id=deck_id,
                    user_id=user_id,
                    slide_id=sid,
                    feedback=feedback,
                )
            except Exception:
                pass

        return deck, issues

    def generate_deck(
        self,
        *,
        user_id: str,
        template_id: str,
        genie_space_id: str,
        google_slides_template_id: str,
        user_prompt: Optional[str],
        tokens: dict[str, Any],
        theme_markdown: str,
        widgets: list[WidgetInfo],
        widget_charts: dict[str, str] | None = None,
        chart_warnings: list[str] | None = None,
        preset_id: str | None = None,
        outline: list[dict] | None = None,
        questions: list[str] | None = None,
    ) -> Deck:
        raw = self._llm.generate_deck_html(
            tokens=tokens,
            theme_markdown=theme_markdown,
            widgets=widgets,
            user_prompt=user_prompt or "",
            widget_chart_ids=list((widget_charts or {}).keys()),
            outline=outline,
        )
        html = sanitize_deck_html(_strip_markdown_fence(raw))
        if outline:
            html = self._reconcile_layouts_with_outline(
                html,
                outline,
                tokens=tokens,
                theme_markdown=theme_markdown,
            )
        html = _normalize_slide_sections(html)
        html = _normalize_deck_css(html)
        html = _normalize_accent_markers(html)
        html = _strip_empty_decorative_divs(html)
        html = _strip_llm_footer_triplet(html)
        if widget_charts:
            html = _inject_widget_chart_srcs(html, widget_charts)
        brand_css = get_brand_css(preset_id)
        if brand_css:
            html = inject_brand_css(html, brand_css)
        _validate_deck_invariants(html)
        deck = Deck(
            id=str(uuid.uuid4()),
            user_id=user_id,
            template_id=template_id,
            genie_space_id=genie_space_id,
            questions=questions or [],
            google_slides_template_id=google_slides_template_id,
            user_prompt=user_prompt,
            html_doc=html,
            design_tokens=tokens,
            theme_markdown=theme_markdown,
            status="draft",
            chart_warnings=list(chart_warnings or []),
        )
        self._repo.insert_deck(deck)
        try:
            self._repo.insert_revision(
                DeckRevision(
                    id=str(uuid.uuid4()),
                    deck_id=deck.id,
                    revision_no=1,
                    html_doc=html,
                    trigger="generate",
                    comment_note=None,
                )
            )
        except Exception:
            self._repo.delete_deck(deck.id, user_id)
            raise
        return deck

    def import_deck_from_pptx(
        self,
        *,
        user_id: str,
        template_id: str,
        pptx_bytes: bytes,
        preset_id: str | None = None,
        design_tokens: dict[str, Any] | None = None,
        theme_markdown: str = "",
        genie_space_id: str = "",
        google_slides_template_id: str = "",
    ) -> Deck:
        """Import an existing .pptx into a new Deck."""
        extracted = extract_slides_from_pptx(pptx_bytes)
        if not extracted:
            raise DeckValidationError("PPTX contained no slides")
        html = build_html_from_extracted(extracted, deck_title="Imported Deck")
        html = sanitize_deck_html(html)
        html = _normalize_slide_sections(html)
        html = _normalize_deck_css(html)
        html = _normalize_accent_markers(html)
        html = _strip_empty_decorative_divs(html)
        brand_css = get_brand_css(preset_id)
        if brand_css:
            html = inject_brand_css(html, brand_css)
        _validate_deck_invariants(html)
        tokens = design_tokens if design_tokens is not None else {}
        deck = Deck(
            id=str(uuid.uuid4()),
            user_id=user_id,
            template_id=template_id,
            genie_space_id=genie_space_id,
            google_slides_template_id=google_slides_template_id,
            user_prompt=None,
            html_doc=html,
            design_tokens=tokens,
            theme_markdown=theme_markdown,
            status="draft",
        )
        self._repo.insert_deck(deck)
        try:
            self._repo.insert_revision(
                DeckRevision(
                    id=str(uuid.uuid4()),
                    deck_id=deck.id,
                    revision_no=1,
                    html_doc=html,
                    trigger="import_pptx",
                    comment_note=None,
                )
            )
        except Exception:
            self._repo.delete_deck(deck.id, user_id)
            raise
        return deck

    def save_comment(
        self, *, deck_id: str, user_id: str, target_id: str, note: str
    ) -> tuple[Deck, int]:
        deck = self._require_deck(deck_id, user_id)
        previous_html = deck.html_doc
        new_html, _marker = insert_marker(
            deck.html_doc, target_id=target_id, note=note, ts=_now_iso()
        )
        new_html = sanitize_deck_html(new_html)
        _validate_deck_invariants(new_html)
        next_rev = self._repo.count_revisions(deck_id) + 1
        self._repo.update_deck_html(deck_id, new_html)
        try:
            self._repo.insert_revision(
                DeckRevision(
                    id=str(uuid.uuid4()),
                    deck_id=deck_id,
                    revision_no=next_rev,
                    html_doc=new_html,
                    trigger="manual_edit",
                    comment_note=note,
                )
            )
        except Exception:
            self._repo.update_deck_html(deck_id, previous_html)
            raise
        self._prune_revisions(deck_id)
        deck.html_doc = new_html
        return deck, next_rev

    def apply_comment(
        self, *, deck_id: str, user_id: str, comment_id: str
    ) -> tuple[Deck, int]:
        deck = self._require_deck(deck_id, user_id)
        marker = find_marker(deck.html_doc, comment_id)
        if marker is None:
            raise DeckValidationError(f"comment {comment_id} not found")
        soup = _parse(deck.html_doc)
        target_el = soup.find(attrs={"data-osd-id": marker.target_id})
        if target_el is None:
            raise DeckValidationError(f"target {marker.target_id} not found in deck")
        slide_section = target_el.find_parent("section", class_="slide") or target_el
        target_id_actual = marker.target_id

        # Chart PNGs are 250-500 KB each; including their base64 src in the
        # prompt blows the input token budget and the endpoint 400s. The
        # validator re-attaches the original src after rewrite.
        def _stripped(node: Any) -> str:
            clone = copy(node)
            for img in clone.find_all("img"):
                if _has_data_image_src(img):
                    img["src"] = ""
            return str(clone)

        target_outer = _stripped(target_el)
        slide_excerpt = (
            target_outer if target_el is slide_section else _stripped(slide_section)
        )
        slide_root_info = _slide_root_info(soup, target_id_actual)

        merged: str | None = None
        for attempt in (1, 2):
            new_subtree = _strip_markdown_fence(
                self._llm.rewrite_element(
                    target_outer_html=target_outer,
                    slide_excerpt=slide_excerpt,
                    tokens=deck.design_tokens,
                    theme_markdown=deck.theme_markdown,
                    note=marker.note,
                )
            )
            try:
                merged = self._validated_merge_rewrite(
                    deck.html_doc, target_id_actual, new_subtree, slide_root_info
                )
                break
            except DeckValidationError:
                if attempt == 2:
                    raise

        assert merged is not None
        merged = sanitize_deck_html(merged)
        _validate_deck_invariants(merged)
        previous_html = deck.html_doc
        next_rev = self._repo.count_revisions(deck_id) + 1
        self._repo.update_deck_html(deck_id, merged)
        try:
            self._repo.insert_revision(
                DeckRevision(
                    id=str(uuid.uuid4()),
                    deck_id=deck_id,
                    revision_no=next_rev,
                    html_doc=merged,
                    trigger="ai_edit",
                    comment_note=marker.note,
                )
            )
        except Exception:
            self._repo.update_deck_html(deck_id, previous_html)
            raise
        self._prune_revisions(deck_id)
        deck.html_doc = merged
        return deck, next_rev

    def _validated_merge_rewrite(
        self,
        deck_html: str,
        target_id: str,
        new_subtree_html: str,
        slide_root_info: _SlideRootInfo,
    ) -> str:
        sub_soup = BeautifulSoup(new_subtree_html, "html.parser")
        for c in list(sub_soup.find_all(string=lambda s: isinstance(s, Comment))):
            if OSD_COMMENT_RE.fullmatch(str(c).strip()):
                c.extract()
        roots = [c for c in sub_soup.children if getattr(c, "name", None)]
        if len(roots) != 1:
            raise DeckValidationError(f"expected 1 root element, got {len(roots)}")
        root = roots[0]
        if root.get("data-osd-id") != target_id:
            raise DeckValidationError("root data-osd-id mismatch")
        if slide_root_info.is_slide_root:
            if root.name != "section":
                raise DeckValidationError("slide root must remain <section>")
            if "slide" not in (root.get("class") or []):
                raise DeckValidationError("slide root must keep 'slide' class")
            if root.get("data-slide-id") != slide_root_info.data_slide_id:
                raise DeckValidationError("slide data-slide-id must not change")

        deck_soup = _parse(deck_html)
        target_e = deck_soup.find(attrs={"data-osd-id": target_id})
        if target_e is None:
            raise DeckValidationError("target lost during rewrite")

        # Chart-img preservation. LLM has no access to the underlying spec,
        # so any hand-coded chart is a correctness violation. If a chart
        # img is missing in the LLM's response, re-inject the original;
        # if present but src was stripped (we strip on input), restore it.
        def _by_widget_id(node: Any) -> dict[str, Any]:
            mapping: dict[str, Any] = {}
            for img in node.find_all("img", class_="widget-chart"):
                wid = img.get("data-widget-id")
                if wid and wid not in mapping:
                    mapping[wid] = img
            return mapping

        orig_imgs = _by_widget_id(target_e)
        new_imgs = _by_widget_id(root)
        for wid, orig_img in orig_imgs.items():
            new_img = new_imgs.get(wid)
            if new_img is None:
                root.append(copy(orig_img))
                continue
            if not _has_data_image_src(new_img):
                orig_src = orig_img.get("src") or ""
                if orig_src:
                    new_img["src"] = orig_src

        target_e.replace_with(root)
        return str(deck_soup)

    def list_pending_comments(
        self, *, deck_id: str, user_id: str
    ) -> list[PendingComment]:
        deck = self._require_deck(deck_id, user_id)
        return [
            PendingComment(id=m.id, target_id=m.target_id, note=m.note, ts=m.ts)
            for m in list_markers(deck.html_doc)
        ]

    def discard_comment(
        self, *, deck_id: str, user_id: str, comment_id: str
    ) -> tuple[Deck, int]:
        deck = self._require_deck(deck_id, user_id)
        previous_html = deck.html_doc
        new_html = remove_marker(deck.html_doc, comment_id)
        new_html = sanitize_deck_html(new_html)
        _validate_deck_invariants(new_html)
        next_rev = self._repo.count_revisions(deck_id) + 1
        self._repo.update_deck_html(deck_id, new_html)
        try:
            self._repo.insert_revision(
                DeckRevision(
                    id=str(uuid.uuid4()),
                    deck_id=deck_id,
                    revision_no=next_rev,
                    html_doc=new_html,
                    trigger="manual_edit",
                    comment_note=None,
                )
            )
        except Exception:
            self._repo.update_deck_html(deck_id, previous_html)
            raise
        self._prune_revisions(deck_id)
        deck.html_doc = new_html
        return deck, next_rev

    def add_slide(self, *, deck_id: str, user_id: str, prompt: str) -> tuple[Deck, int]:
        deck = self._require_deck(deck_id, user_id)
        merged: str | None = None
        for attempt in (1, 2):
            raw_section = _strip_markdown_fence(
                self._llm.generate_slide_section(
                    deck_html=deck.html_doc,
                    tokens=deck.design_tokens,
                    theme_markdown=deck.theme_markdown,
                    user_prompt=prompt,
                )
            )
            try:
                merged = self._merge_new_slide(deck.html_doc, raw_section)
                break
            except DeckValidationError:
                if attempt == 2:
                    raise

        assert merged is not None
        merged = sanitize_deck_html(merged)
        _validate_deck_invariants(merged)
        next_rev = self._repo.count_revisions(deck_id) + 1
        self._repo.update_deck_html(deck_id, merged)
        self._repo.insert_revision(
            DeckRevision(
                id=str(uuid.uuid4()),
                deck_id=deck_id,
                revision_no=next_rev,
                html_doc=merged,
                trigger="ai_edit",
                comment_note=None,
            )
        )
        self._prune_revisions(deck_id)
        deck.html_doc = merged
        return deck, next_rev

    def _merge_new_slide(self, deck_html: str, new_section_html: str) -> str:
        sub = BeautifulSoup(new_section_html, "html.parser")
        roots = [c for c in sub.children if getattr(c, "name", None)]
        if len(roots) != 1:
            raise DeckValidationError(f"add-slide expected 1 root, got {len(roots)}")
        root = roots[0]
        if root.name != "section" or "slide" not in (root.get("class") or []):
            raise DeckValidationError('add-slide root must be <section class="slide">')
        if not root.get("data-slide-id") or not root.get("data-osd-id"):
            raise DeckValidationError(
                "add-slide root must have data-slide-id and data-osd-id"
            )

        deck_soup = _parse(deck_html)
        existing_ids = set(_all_osd_ids(deck_soup))
        existing_slide_ids = set(_all_slide_ids(deck_soup))

        def _fresh_id(existing: set[str]) -> str:
            while True:
                nid = generate_element_id()
                if nid not in existing:
                    existing.add(nid)
                    return nid

        if root.get("data-slide-id") in existing_slide_ids:
            root["data-slide-id"] = "s" + secrets.token_hex(3)
        existing_slide_ids.add(str(root.get("data-slide-id")))
        for el in [root, *root.find_all(attrs={"data-osd-id": True})]:
            cur = el.get("data-osd-id")
            if not cur or cur in existing_ids:
                el["data-osd-id"] = _fresh_id(existing_ids)
            else:
                existing_ids.add(str(cur))

        body = deck_soup.find("body") or deck_soup
        body.append(root)
        return str(deck_soup)

    def delete_slide(
        self, *, deck_id: str, user_id: str, slide_id: str
    ) -> tuple[Deck, int]:
        deck = self._require_deck(deck_id, user_id)
        soup = _parse(deck.html_doc)
        target = soup.find("section", attrs={"data-slide-id": slide_id})
        if target is None:
            raise DeckValidationError(f"slide {slide_id} not found")
        target.extract()
        new_html = sanitize_deck_html(str(soup))
        _validate_deck_invariants(new_html)
        next_rev = self._repo.count_revisions(deck_id) + 1
        self._repo.update_deck_html(deck_id, new_html)
        self._repo.insert_revision(
            DeckRevision(
                id=str(uuid.uuid4()),
                deck_id=deck_id,
                revision_no=next_rev,
                html_doc=new_html,
                trigger="manual_edit",
                comment_note=None,
            )
        )
        self._prune_revisions(deck_id)
        deck.html_doc = new_html
        return deck, next_rev

    def regenerate_slide(
        self, *, deck_id: str, user_id: str, slide_id: str, feedback: str = ""
    ) -> tuple[Deck, int]:
        deck = self._require_deck(deck_id, user_id)
        soup = _parse(deck.html_doc)
        target = soup.find("section", attrs={"data-slide-id": slide_id})
        if target is None:
            raise DeckValidationError(f"slide not found: {slide_id}")
        old_outer = str(target)

        merged: str | None = None
        for attempt in (1, 2):
            raw_section = _strip_markdown_fence(
                self._llm.regenerate_slide_section(
                    deck_html=deck.html_doc,
                    slide_outer_html=old_outer,
                    tokens=deck.design_tokens,
                    theme_markdown=deck.theme_markdown,
                    feedback=feedback,
                )
            )
            try:
                merged = self._replace_slide(deck.html_doc, slide_id, raw_section)
                break
            except DeckValidationError:
                if attempt == 2:
                    raise

        assert merged is not None
        merged = sanitize_deck_html(merged)
        merged = _normalize_slide_sections(merged)
        merged = _normalize_deck_css(merged)
        merged = _normalize_accent_markers(merged)
        merged = _strip_empty_decorative_divs(merged)
        merged = _strip_llm_footer_triplet(merged)
        _validate_deck_invariants(merged)

        next_rev = self._repo.count_revisions(deck_id) + 1
        self._repo.update_deck_html(deck_id, merged)
        self._repo.insert_revision(
            DeckRevision(
                id=str(uuid.uuid4()),
                deck_id=deck_id,
                revision_no=next_rev,
                html_doc=merged,
                trigger="regenerate_slide",
                comment_note=feedback or None,
            )
        )
        self._prune_revisions(deck_id)
        deck.html_doc = merged
        return deck, next_rev

    def _replace_slide(
        self, deck_html: str, slide_id: str, new_section_html: str
    ) -> str:
        sub = BeautifulSoup(new_section_html, "html.parser")
        roots = [c for c in sub.children if getattr(c, "name", None)]
        if len(roots) != 1:
            raise DeckValidationError(
                f"regenerate-slide expected 1 root, got {len(roots)}"
            )
        root = roots[0]
        if root.name != "section" or "slide" not in (root.get("class") or []):
            raise DeckValidationError(
                'regenerate-slide root must be <section class="slide">'
            )

        root["data-slide-id"] = slide_id

        deck_soup = _parse(deck_html)
        target = deck_soup.find("section", attrs={"data-slide-id": slide_id})
        if target is None:
            raise DeckValidationError(f"slide not found in deck: {slide_id}")

        existing_ids = set(_all_osd_ids(deck_soup))
        for el in [target, *target.find_all(attrs={"data-osd-id": True})]:
            existing_ids.discard(el.get("data-osd-id", ""))

        for el in [root, *root.find_all(attrs={"data-osd-id": True})]:
            cur = el.get("data-osd-id")
            if not cur or cur in existing_ids:
                new_id = generate_element_id()
                while new_id in existing_ids:
                    new_id = generate_element_id()
                el["data-osd-id"] = new_id
                existing_ids.add(new_id)
            else:
                existing_ids.add(str(cur))

        target.replace_with(root)
        return str(deck_soup)

    def _require_deck(self, deck_id: str, user_id: str) -> Deck:
        d = self._repo.get_deck(deck_id, user_id)
        if d is None:
            raise DeckValidationError(f"deck {deck_id} not found for user")
        return d

    def _prune_revisions(self, deck_id: str) -> None:
        if self._repo.count_revisions(deck_id) > _MAX_REVISIONS:
            self._repo.delete_oldest_non_genesis_revision(deck_id)


class DeckUCRepo:
    """UC SQL implementation of DeckRepo. Mirrors TemplateService's sql_client pattern."""

    def __init__(self, *, sql_client: Any, catalog: str, schema: str) -> None:
        self._c = sql_client
        self._catalog = catalog
        self._schema = schema

    @staticmethod
    def _q(v: str) -> str:
        # Escape backslash FIRST (so we don't re-escape the backslashes we add for quotes),
        # then double single quotes. Defensive against clusters where
        # spark.sql.parser.escapedStringLiterals=false honors C-style escapes.
        return v.replace("\\", "\\\\").replace("'", "''")

    @classmethod
    def _opt(cls, v: Optional[str]) -> str:
        """Render NULL or quoted SQL literal. Avoids nested f-strings (Python 3.11)."""
        return "NULL" if v is None else "'" + cls._q(v) + "'"

    def _t(self, name: str) -> str:
        return f"`{self._catalog}`.`{self._schema}`.`{name}`"

    def _deck_from_row(self, row: Any) -> Deck:
        gslides_file_id = row[12] if len(row) > 12 else None
        gslides_url = row[13] if len(row) > 13 else None
        return Deck(
            id=row[0],
            user_id=row[1],
            template_id=row[2],
            genie_space_id=row[3],
            google_slides_template_id=row[4] or "",
            user_prompt=row[5],
            html_doc=row[6],
            design_tokens=json.loads(row[7] or "{}"),
            theme_markdown=row[8] or "",
            status=row[9],
            created_at=row[10],
            updated_at=row[11],
            gslides_file_id=gslides_file_id,
            gslides_url=gslides_url,
        )

    def insert_deck(self, deck: Deck) -> None:
        cols = (
            "id, user_id, template_id, genie_space_id, google_slides_template_id, "
            "user_prompt, html_doc, design_tokens, theme_markdown, status, "
            "created_at, updated_at, gslides_file_id, gslides_url"
        )
        values = (
            f"'{self._q(deck.id)}', '{self._q(deck.user_id)}', "
            f"'{self._q(deck.template_id)}', '{self._q(deck.genie_space_id)}', "
            f"'{self._q(deck.google_slides_template_id)}', "
            f"{self._opt(deck.user_prompt)}, "
            f"'{self._q(deck.html_doc)}', "
            f"'{self._q(json.dumps(deck.design_tokens))}', "
            f"'{self._q(deck.theme_markdown)}', '{self._q(deck.status)}', "
            f"current_timestamp(), current_timestamp(), "
            f"{self._opt(deck.gslides_file_id)}, {self._opt(deck.gslides_url)}"
        )
        self._c.execute(f"INSERT INTO {self._t('decks')} ({cols}) VALUES ({values})")

    def get_deck(self, deck_id: str, user_id: str) -> Deck | None:
        cols = (
            "id, user_id, template_id, genie_space_id, google_slides_template_id, "
            "user_prompt, html_doc, design_tokens, theme_markdown, status, "
            "created_at, updated_at, gslides_file_id, gslides_url"
        )
        sql = (
            f"SELECT {cols} FROM {self._t('decks')} "
            f"WHERE id = '{self._q(deck_id)}' AND user_id = '{self._q(user_id)}'"
        )
        row = self._c.fetchone(sql)
        if row is None:
            return None
        return self._deck_from_row(row)

    def list_decks(self, user_id: str) -> list[Deck]:
        cols = (
            "id, user_id, template_id, genie_space_id, google_slides_template_id, "
            "user_prompt, html_doc, design_tokens, theme_markdown, status, "
            "created_at, updated_at, gslides_file_id, gslides_url"
        )
        sql = (
            f"SELECT {cols} FROM {self._t('decks')} "
            f"WHERE user_id = '{self._q(user_id)}' ORDER BY created_at DESC LIMIT 1000"
        )
        rows = self._c.fetchall(sql)
        return [self._deck_from_row(row) for row in rows]

    def update_deck_html(self, deck_id: str, html_doc: str) -> None:
        sql = (
            f"UPDATE {self._t('decks')} SET html_doc = '{self._q(html_doc)}', "
            f"updated_at = current_timestamp() WHERE id = '{self._q(deck_id)}'"
        )
        self._c.execute(sql)

    def update_deck_gslides_link(
        self, deck_id: str, user_id: str, file_id: str, url: str
    ) -> None:
        sql = (
            f"UPDATE {self._t('decks')} SET "
            f"gslides_file_id = '{self._q(file_id)}', "
            f"gslides_url = '{self._q(url)}', "
            f"updated_at = current_timestamp() "
            f"WHERE id = '{self._q(deck_id)}' AND user_id = '{self._q(user_id)}'"
        )
        self._c.execute(sql)

    def insert_revision(self, rev: DeckRevision) -> None:
        cols = "id, deck_id, revision_no, html_doc, trigger, comment_note, created_at"
        values = (
            f"'{self._q(rev.id)}', '{self._q(rev.deck_id)}', {rev.revision_no}, "
            f"'{self._q(rev.html_doc)}', '{self._q(rev.trigger)}', "
            f"{self._opt(rev.comment_note)}, current_timestamp()"
        )
        self._c.execute(
            f"INSERT INTO {self._t('deck_revisions')} ({cols}) VALUES ({values})"
        )

    def count_revisions(self, deck_id: str) -> int:
        sql = (
            f"SELECT count(*) FROM {self._t('deck_revisions')} "
            f"WHERE deck_id = '{self._q(deck_id)}'"
        )
        row = self._c.fetchone(sql)
        return int(row[0]) if row else 0

    def delete_oldest_non_genesis_revision(self, deck_id: str) -> None:
        # Demo simplification: delete the lowest revision_no > 1 for this deck.
        t = self._t("deck_revisions")
        did = self._q(deck_id)
        sql = (
            f"DELETE FROM {t} "
            f"WHERE deck_id = '{did}' AND revision_no = ("
            f"  SELECT MIN(revision_no) FROM {t} "
            f"  WHERE deck_id = '{did}' AND revision_no > 1"
            f")"
        )
        self._c.execute(sql)

    def delete_deck(self, deck_id: str, user_id: str) -> None:
        did = self._q(deck_id)
        uid = self._q(user_id)
        self._c.execute(
            f"DELETE FROM {self._t('deck_revisions')} WHERE deck_id = '{did}'"
        )
        self._c.execute(
            f"DELETE FROM {self._t('decks')} WHERE id = '{did}' AND user_id = '{uid}'"
        )


class DeckMemoryRepo:
    """In-memory DeckRepo for demos and tests.

    Pass ``persist_path`` to opt into JSON file persistence — decks and
    revisions are loaded on init and rewritten to disk on every mutation.
    Demo-grade only (single-process, no locking).
    """

    def __init__(self, persist_path: str | None = None) -> None:
        self._decks: dict[str, Deck] = {}
        self._revisions: dict[str, list[DeckRevision]] = {}
        self._persist_path = persist_path
        if persist_path:
            self._load()

    def _load(self) -> None:
        import json as _json
        import os as _os

        path = self._persist_path
        if not path or not _os.path.exists(path):
            return
        try:
            with open(path, "r") as f:
                data = _json.load(f)
            for raw in data.get("decks", []):
                deck = Deck.model_validate(raw)
                self._decks[deck.id] = deck
            for deck_id, raw_revs in data.get("revisions", {}).items():
                self._revisions[deck_id] = [
                    DeckRevision.model_validate(r) for r in raw_revs
                ]
        except Exception:
            pass

    def _save(self) -> None:
        import json as _json
        import os as _os

        path = self._persist_path
        if not path:
            return
        _os.makedirs(_os.path.dirname(path) or ".", exist_ok=True)
        payload = {
            "decks": [d.model_dump(mode="json") for d in self._decks.values()],
            "revisions": {
                k: [r.model_dump(mode="json") for r in v]
                for k, v in self._revisions.items()
            },
        }
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            _json.dump(payload, f)
        _os.replace(tmp, path)

    def clear(self) -> None:
        self._decks.clear()
        self._revisions.clear()
        self._save()

    def insert_deck(self, deck: Deck) -> None:
        now = datetime.now(tz=timezone.utc)
        if deck.created_at is None:
            deck.created_at = now
        if deck.updated_at is None:
            deck.updated_at = now
        self._decks[deck.id] = deck
        self._revisions.setdefault(deck.id, [])
        self._save()

    def get_deck(self, deck_id: str, user_id: str) -> Deck | None:
        d = self._decks.get(deck_id)
        if d is None or d.user_id != user_id:
            return None
        return d

    def list_decks(self, user_id: str) -> list[Deck]:
        rows = [d for d in self._decks.values() if d.user_id == user_id]
        rows.sort(
            key=lambda d: d.created_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return rows

    def update_deck_html(self, deck_id: str, html_doc: str) -> None:
        d = self._decks.get(deck_id)
        if d is None:
            return
        d.html_doc = html_doc
        d.updated_at = datetime.now(tz=timezone.utc)
        self._save()

    def update_deck_gslides_link(
        self, deck_id: str, user_id: str, file_id: str, url: str
    ) -> None:
        d = self._decks.get(deck_id)
        if d is None or d.user_id != user_id:
            return
        d.gslides_file_id = file_id
        d.gslides_url = url
        d.updated_at = datetime.now(tz=timezone.utc)
        self._save()

    def insert_revision(self, rev: DeckRevision) -> None:
        self._revisions.setdefault(rev.deck_id, []).append(rev)
        self._save()

    def count_revisions(self, deck_id: str) -> int:
        return len(self._revisions.get(deck_id, []))

    def delete_oldest_non_genesis_revision(self, deck_id: str) -> None:
        revs = self._revisions.get(deck_id, [])
        candidates = [r for r in revs if r.revision_no > 1]
        if not candidates:
            return
        oldest = min(candidates, key=lambda r: r.revision_no)
        self._revisions[deck_id] = [r for r in revs if r.id != oldest.id]
        self._save()

    def delete_deck(self, deck_id: str, user_id: str) -> None:
        d = self._decks.get(deck_id)
        if d is None or d.user_id != user_id:
            return
        del self._decks[deck_id]
        self._revisions.pop(deck_id, None)
        self._save()
