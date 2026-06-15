"""Smoke test for the HTML→PDF builder. Validates that Playwright can
render a tiny synthetic deck and produces a non-empty PDF payload."""

from services.pdf_export_service import _build_print_html, export_deck_html_to_pdf


def test_build_print_html_inserts_style():
    deck = "<html><head><title>x</title></head><body><section class='slide'>hi</section></body></html>"
    out = _build_print_html(deck)
    assert 'data-print="deck"' in out
    assert "size: 1920px 1080px" in out
    # Style block placed before </head>
    style_idx = out.index('data-print="deck"')
    head_close_idx = out.index("</head>")
    assert style_idx < head_close_idx


def test_build_print_html_defensive_no_head():
    deck = "<section class='slide'>no head</section>"
    out = _build_print_html(deck)
    assert "<head>" in out
    assert 'data-print="deck"' in out


def test_export_deck_html_to_pdf_smoke():
    # Minimal valid deck HTML with one slide section
    deck = (
        "<!DOCTYPE html><html><head><title>Test</title>"
        "<style>body{font-family:sans-serif}</style>"
        "</head><body>"
        "<section class='slide' data-osd-id='el-1'>"
        "<h1>Hello</h1><p>Slide content</p>"
        "</section>"
        "</body></html>"
    )
    pdf_bytes = export_deck_html_to_pdf(deck)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    # PDF magic bytes
    assert pdf_bytes.startswith(b"%PDF")
