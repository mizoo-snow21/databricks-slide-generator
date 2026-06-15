"""Write-time HTML sanitizer for editable deck documents.

All persistence paths must run output through `sanitize_deck_html` before
storing in `decks.html_doc`. The sanitizer is allowlist-based and preserves
`<!--osd-comment ...-->` markers verbatim while stripping all other HTML
comments, scripts, external resource URLs, and other dangerous constructs.
"""

from __future__ import annotations

import re

import bleach
from bleach.css_sanitizer import CSSSanitizer
from bs4 import BeautifulSoup, Comment

_ALLOWED_TAGS: list[str] = [
    "html",
    "head",
    "body",
    "title",
    "style",
    "section",
    "div",
    "span",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
    "ul",
    "ol",
    "li",
    "strong",
    "em",
    "b",
    "i",
    "u",
    "img",
    "br",
    "hr",
    "svg",
    "g",
    "path",
    "rect",
    "circle",
    "ellipse",
    "line",
    "polyline",
    "polygon",
    "text",
    "tspan",
    "defs",
    "linearGradient",
    "radialGradient",
    "stop",
]

_ALLOWED_ATTRS: dict[str, list[str]] = {
    "*": [
        "class",
        "style",
        "data-osd-id",
        "data-slide-id",
        "data-layout",
        "id",
    ],
    "img": ["src", "alt", "width", "height", "data-widget-id"],
    "svg": ["viewBox", "width", "height", "xmlns", "preserveAspectRatio", "fill"],
    "path": [
        "d",
        "fill",
        "stroke",
        "stroke-width",
        "stroke-linecap",
        "stroke-linejoin",
    ],
    "rect": ["x", "y", "width", "height", "rx", "ry", "fill", "stroke"],
    "circle": ["cx", "cy", "r", "fill", "stroke"],
    "ellipse": ["cx", "cy", "rx", "ry", "fill", "stroke"],
    "line": ["x1", "y1", "x2", "y2", "stroke", "stroke-width"],
    "polyline": ["points", "fill", "stroke"],
    "polygon": ["points", "fill", "stroke"],
    "text": ["x", "y", "fill", "font-size", "text-anchor"],
    "tspan": ["x", "y", "fill", "font-size"],
    "linearGradient": ["x1", "y1", "x2", "y2"],
    "radialGradient": ["cx", "cy", "r"],
    "stop": ["offset", "stop-color"],
}

_OSD_COMMENT_RE = re.compile(
    r'osd-comment\s+id="c-[a-f0-9]{4,8}"\s+target="[^"]+"\s+ts="[^"]+"\s+note="[^"]*"'
)

# bleach strips <html>/<head>/<body> even when allowlisted — detect explicit wrappers in input.
_HAS_HTML_ROOT_RE = re.compile(r"<\s*html\b", re.IGNORECASE)

_AT_IMPORT_RE = re.compile(r"@import[^;]+;", re.IGNORECASE)
_CSS_BAD_RE = re.compile(r"(expression\s*\(|behavior\s*:)", re.IGNORECASE)
_URL_UNQUOTED_RE = re.compile(r"url\(\s*([^\"'()]+?)\s*\)", re.IGNORECASE)
_URL_QUOTED_RE = re.compile(r'url\(\s*(["\'])([^"\']*)\1\s*\)', re.IGNORECASE)


def _comment_inner(raw: str) -> str:
    t = raw.strip()
    if t.startswith("<!--") and t.endswith("-->"):
        return t[4:-3].strip()
    return t


def _is_allowed_resource_url(url: str) -> bool:
    u = url.strip()
    if u.lower().startswith("data:image/"):
        return True
    if u.startswith("/") and not u.startswith("//"):
        return True
    return False


def _sanitize_css(css: str) -> str:
    css = _AT_IMPORT_RE.sub("", css)
    css = _CSS_BAD_RE.sub("", css)

    def sub_quoted(m: re.Match[str]) -> str:
        url = m.group(2).strip()
        if _is_allowed_resource_url(url):
            return m.group(0)
        return ""

    css = _URL_QUOTED_RE.sub(sub_quoted, css)

    def sub_unquoted(m: re.Match[str]) -> str:
        url = m.group(1).strip()
        if _is_allowed_resource_url(url):
            return f"url({url})"
        return ""

    css = _URL_UNQUOTED_RE.sub(sub_unquoted, css)
    return css


_CSS_SANITIZER = CSSSanitizer(
    allowed_css_properties=[
        "color",
        "background",
        "background-color",
        "background-image",
        "margin",
        "padding",
        "width",
        "height",
        "display",
        "border",
        "font-size",
        "font-family",
        "font-weight",
        "text-align",
        "line-height",
        "opacity",
        "fill",
        "stroke",
        "stroke-width",
        "stop-color",
    ],
)


def _rewrap_bleached_fragment_as_document(shell_html: str) -> str:
    """Rebuild html/head/body wrappers bleach strips from allowlisted markup.

    Splits the bleached fragment so <title> and <style> go in <head> and
    everything else goes in <body>, then wraps with <html>...</html>.
    """
    fragment = BeautifulSoup(shell_html, "html.parser")
    head_parts: list[str] = []
    body_parts: list[str] = []
    for child in list(fragment.children):
        name = getattr(child, "name", None)
        if name in ("title", "style"):
            head_parts.append(str(child))
        else:
            body_parts.append(str(child))
    # Baseline guards (cheap CSS) so LLM-authored slides don't break in
    # predictable ways. Appended AFTER LLM styles so later rules win
    # ties only via specificity; using a low-specificity selector here.
    baseline = (
        "<style>"
        ".slide-title,.slide h1,.slide h2,.slide h3{"
        "word-break:break-word;overflow-wrap:anywhere;max-width:100%;"
        "}"
        "</style>"
    )
    return (
        "<!doctype html>"
        "<html><head>"
        + "".join(head_parts)
        + baseline
        + "</head><body>"
        + "".join(body_parts)
        + "</body></html>"
    )


def sanitize_deck_html(html: str) -> str:
    """Sanitize a full HTML deck document.

    - Strips disallowed tags/attrs (script, iframe, on*, etc.)
    - Strips external resource URLs in <img src>, style url(), and stylesheet @import
    - Removes all HTML comments EXCEPT osd-comment markers (preserved verbatim)
    - Returns a string; output is always already-sanitized.
    """
    if not html:
        return ""

    preserve_document_shell = _HAS_HTML_ROOT_RE.search(html) is not None

    soup = BeautifulSoup(html, "html.parser")
    placeholder_map: dict[str, str] = {}

    for comment in list(soup.find_all(string=lambda s: isinstance(s, Comment))):
        raw = str(comment).strip()
        inner = _comment_inner(raw)
        if _OSD_COMMENT_RE.fullmatch(inner):
            ph = f"__OSD_COMMENT_PLACEHOLDER_{len(placeholder_map)}__"
            placeholder_map[ph] = raw if raw.startswith("<!--") else f"<!--{inner}-->"
            comment.replace_with(ph)
        else:
            comment.extract()

    for style in soup.find_all("style"):
        pieces = list(style.strings)
        if not pieces:
            continue
        combined = "".join(str(s) for s in pieces)
        new_css = _sanitize_css(combined)
        style.clear()
        style.append(new_css)

    for el in soup.find_all(True):
        if el.has_attr("style"):
            el["style"] = _sanitize_css(el["style"])
        if el.name == "img" and el.has_attr("src"):
            if not _is_allowed_resource_url(el["src"]):
                del el["src"]

    # Tag chart-card divs so comment-apply targets them directly instead
    # of escalating all the way to the slide section.
    def _chart_card_to_tag(img: Any) -> Any:
        """Return the outermost <div> ancestor inside the slide section
        that has no data-osd-id, or None if one already exists."""
        slide_root = img.find_parent("section", class_="slide")
        outermost = None
        for anc in img.parents:
            if anc is slide_root:
                break
            if anc.name == "div":
                if anc.get("data-osd-id"):
                    return None
                outermost = anc
        return outermost

    existing_osd_ids: set[str] = {
        el["data-osd-id"]
        for el in soup.find_all(attrs={"data-osd-id": True})
        if el.get("data-osd-id")
    }

    for n, img in enumerate(soup.find_all("img", class_="widget-chart"), start=1):
        card = _chart_card_to_tag(img)
        if card is None:
            continue
        slide = card.find_parent("section", class_="slide")
        prefix = (slide.get("data-slide-id") if slide else None) or "slide"
        candidate = f"{prefix}-card-{n}"
        while candidate in existing_osd_ids:
            n += 1
            candidate = f"{prefix}-card-{n}"
        card["data-osd-id"] = candidate
        existing_osd_ids.add(candidate)

    intermediate = str(soup)

    cleaned = bleach.clean(
        intermediate,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        protocols=["data", "https"],
        strip=True,
        strip_comments=False,
        css_sanitizer=_CSS_SANITIZER,
    )

    for ph, original in placeholder_map.items():
        cleaned = cleaned.replace(ph, original)

    if preserve_document_shell:
        cleaned = _rewrap_bleached_fragment_as_document(cleaned)

    if cleaned and not cleaned.lstrip().lower().startswith("<!doctype"):
        cleaned = "<!doctype html>" + cleaned

    return cleaned
