"""Render a deck's HTML document to a PDF using Playwright.

The deck HTML contains stacked <section class="slide"> elements. We
inject a print stylesheet that paginates each slide as its own page
matching the slide canvas aspect ratio (1920x1080 → 16:9 landscape).
"""

from __future__ import annotations

import asyncio

PRINT_CSS = """
@page {
  size: 1920px 1080px;
  margin: 0;
}
html, body {
  background: #ffffff !important;
  margin: 0 !important;
  padding: 0 !important;
}
section.slide {
  width: 1920px !important;
  height: 1080px !important;
  break-after: page !important;
  page-break-after: always !important;
  overflow: hidden !important;
}
section.slide:last-child {
  break-after: auto !important;
  page-break-after: auto !important;
}
"""


def _build_print_html(deck_html: str) -> str:
    """Append a print stylesheet to the deck HTML's <head>."""
    style_block = f'<style data-print="deck">{PRINT_CSS}</style>'
    lower = deck_html.lower()
    head_close = lower.find("</head>")
    if head_close == -1:
        # Defensive: prepend a <head> with the style
        return f"<!DOCTYPE html><html><head>{style_block}</head><body>{deck_html}</body></html>"
    return deck_html[:head_close] + style_block + deck_html[head_close:]


async def _render_pdf_async(deck_html: str) -> bytes:
    from playwright.async_api import async_playwright

    print_html = _build_print_html(deck_html)
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox"])
        try:
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080}
            )
            page = await context.new_page()
            await page.set_content(print_html, wait_until="networkidle")
            pdf_bytes = await page.pdf(
                width="1920px",
                height="1080px",
                print_background=True,
                prefer_css_page_size=True,
            )
            return pdf_bytes
        finally:
            await browser.close()


def export_deck_html_to_pdf(deck_html: str) -> bytes:
    """Synchronous wrapper: render the deck HTML to PDF bytes."""
    return asyncio.run(_render_pdf_async(deck_html))
