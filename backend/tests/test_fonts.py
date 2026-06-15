"""Bundled Noto Sans JP font and Vega-Lite font stack expectations."""

from __future__ import annotations

from pathlib import Path

from services.vegalite_service import _FONT_STACK

_NOTO_JP_TTF = (
    Path(__file__).resolve().parent.parent
    / "assets"
    / "fonts"
    / "NotoSansJP-VariableFont.ttf"
)


def test_noto_sans_jp_font_file_exists() -> None:
    assert _NOTO_JP_TTF.is_file()
    assert _NOTO_JP_TTF.stat().st_size > 1_000_000


def test_font_stack_includes_noto_sans_jp() -> None:
    assert "Noto Sans JP" in _FONT_STACK
