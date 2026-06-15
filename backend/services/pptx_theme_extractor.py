"""Extract DesignTokens-shaped dicts from PPTX theme XML (DrawingML)."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from pptx import Presentation

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _qn_a(tag: str) -> str:
    return f"{{{A_NS}}}{tag}"


def _normalize_hex(val: str) -> str:
    h = val.strip().lstrip("#").lower()
    if len(h) == 8:
        h = h[2:]
    if len(h) == 6:
        return f"#{h}"
    return f"#{h}"


def _hex_from_color_container(container: Any) -> str | None:
    """Read hex from a:dk1 / a:accent1 etc. (child srgbClr or sysClr)."""
    if container is None:
        return None
    for child in container:
        tag = child.tag
        if tag == _qn_a("srgbClr"):
            raw = child.get("val")
            if raw:
                return _normalize_hex(raw)
        if tag == _qn_a("sysClr"):
            raw = child.get("lastClr")
            if raw:
                return _normalize_hex(raw)
    return None


def _palette_from_clr_scheme(clr_scheme: Any) -> dict[str, str]:
    defaults = {
        "bg": "#ffffff",
        "text": "#1b3139",
        "accent": "#ff3621",
        "muted": "#6f7989",
    }
    out = dict(defaults)
    mapping = {
        "bg": "lt1",
        "text": "dk1",
        "accent": "accent1",
        "muted": "dk2",
    }
    for key, local in mapping.items():
        node = clr_scheme.find(_qn_a(local))
        if node is None:
            continue
        hx = _hex_from_color_container(node)
        if hx:
            out[key] = hx
    return out


def _latin_typeface(font_scheme: Any, major: bool) -> str | None:
    target = _qn_a("majorFont") if major else _qn_a("minorFont")
    for group in font_scheme:
        if group.tag != target:
            continue
        for child in group:
            if child.tag == _qn_a("latin"):
                face = child.get("typeface")
                if face and face.strip():
                    return face.strip()
    return None


def _fonts_from_font_scheme(font_scheme: Any) -> dict[str, str]:
    default = "'DM Sans', sans-serif"
    display = _latin_typeface(font_scheme, major=True)
    body = _latin_typeface(font_scheme, major=False)
    return {
        "display": (f"'{display}', sans-serif" if display else default),
        "body": f"'{body}', sans-serif" if body else default,
    }


def extract_design_tokens_from_pptx(pptx_bytes: bytes) -> dict[str, Any]:
    """Parse theme colors/fonts from PPTX bytes; fall back to safe defaults on failure."""
    result: dict[str, Any] = {
        "palette": {
            "bg": "#ffffff",
            "text": "#1b3139",
            "accent": "#ff3621",
            "muted": "#6f7989",
        },
        "fonts": {"display": "'DM Sans', sans-serif", "body": "'DM Sans', sans-serif"},
        "typeScale": {"hero": 180, "title": 80, "body": 32, "caption": 22},
        "spacing": {"padding": 120, "gap": 48},
        "radius": 0,
    }
    try:
        prs = Presentation(BytesIO(pptx_bytes))
        sm = prs.slide_masters[0]
        root = sm.part.theme_part.element
        clr_scheme = None
        font_scheme = None
        for el in root.iter():
            if clr_scheme is None and el.tag == _qn_a("clrScheme"):
                clr_scheme = el
            if font_scheme is None and el.tag == _qn_a("fontScheme"):
                font_scheme = el
            if clr_scheme is not None and font_scheme is not None:
                break
        if clr_scheme is not None:
            result["palette"] = _palette_from_clr_scheme(clr_scheme)
        if font_scheme is not None:
            result["fonts"] = _fonts_from_font_scheme(font_scheme)
    except Exception:
        pass
    return result
