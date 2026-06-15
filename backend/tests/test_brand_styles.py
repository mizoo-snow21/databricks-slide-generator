"""Tests for injected brand preset CSS."""

from __future__ import annotations

from services.brand_styles import (
    DATABRICKS_BRAND_BRAND_CSS,
    DATABRICKS_CORP_BRAND_CSS,
    DATABRICKS_CORP_DARK_BRAND_CSS,
)


def test_brand_css_section_divider_has_pointer_events_none() -> None:
    for css in (
        DATABRICKS_CORP_BRAND_CSS,
        DATABRICKS_CORP_DARK_BRAND_CSS,
        DATABRICKS_BRAND_BRAND_CSS,
    ):
        assert "pointer-events: none" in css
