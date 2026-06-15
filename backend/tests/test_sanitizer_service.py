from bs4 import BeautifulSoup

from services.sanitizer_service import sanitize_deck_html


def test_strips_script_tags():
    html = '<html><body><section data-osd-id="el-1"><h1>Hi</h1><script>alert(1)</script></section></body></html>'
    out = sanitize_deck_html(html)
    assert "<script>" not in out
    assert "<h1>Hi</h1>" in out


def test_strips_event_handler_attributes():
    html = '<html><body><div onclick="x()" data-osd-id="el-1">x</div></body></html>'
    out = sanitize_deck_html(html)
    assert "onclick" not in out
    assert 'data-osd-id="el-1"' in out


def test_strips_external_image_src():
    html = (
        '<html><body><img src="https://evil.example.com/leak.png" alt=""></body></html>'
    )
    out = sanitize_deck_html(html)
    assert "evil.example.com" not in out


def test_keeps_data_uri_image():
    src = "data:image/png;base64,iVBORw0KGgo="
    html = f'<html><body><img src="{src}" alt=""></body></html>'
    out = sanitize_deck_html(html)
    assert src in out


def test_strips_external_url_in_style():
    html = '<html><body><div style="background: url(https://evil.example.com/x.png)"></div></body></html>'
    out = sanitize_deck_html(html)
    assert "evil.example.com" not in out


def test_strips_at_import_in_style_block():
    html = "<html><head><style>@import url(https://evil.example.com/x.css); h1 { color: red; }</style></head><body></body></html>"
    out = sanitize_deck_html(html)
    assert "@import" not in out
    assert "color: red" in out


def test_preserves_osd_comment_marker():
    marker = '<!--osd-comment id="c-9b2e" target="el-7a3f" ts="2026-05-07T12:00:00Z" note="abc"-->'
    html = f'<html><body><h1 data-osd-id="el-7a3f">{marker}Title</h1></body></html>'
    out = sanitize_deck_html(html)
    assert marker in out


def test_strips_other_html_comments():
    html = "<html><body><!-- prompt leak --><h1>X</h1><!--[if IE]><![endif]--></body></html>"
    out = sanitize_deck_html(html)
    assert "prompt leak" not in out
    assert "if IE" not in out


def test_keeps_html_head_body_shell():
    html = "<html><head><title>T</title></head><body><h1>X</h1></body></html>"
    out = sanitize_deck_html(html)
    assert out.lstrip().lower().startswith("<!doctype html")
    assert (
        "<html" in out
        and "<head" in out
        and "<body" in out
        and "<title>T</title>" in out
    )


def test_outputs_doctype_for_fragments_without_html_root():
    html = '<section class="slide" data-slide-id="s1"><h1>X</h1></section>'
    out = sanitize_deck_html(html)
    assert out.lstrip().lower().startswith("<!doctype html")


def test_widget_chart_tags_outermost_card_div_not_inner_wrap():
    html = (
        '<section class="slide" data-slide-id="s1">'
        '<div class="card"><h3>Revenue</h3>'
        '<div class="wrap"><img class="widget-chart" data-widget-id="w1"></div>'
        "</div></section>"
    )
    out = sanitize_deck_html(html)
    soup = BeautifulSoup(out, "html.parser")
    card = soup.find("div", class_="card")
    wrap = soup.find("div", class_="wrap")
    assert card is not None and card.get("data-osd-id") == "s1-card-1"
    assert wrap is not None and not wrap.get("data-osd-id")


def test_widget_chart_skips_tagging_when_ancestor_already_has_osd_id():
    html = (
        '<section class="slide" data-slide-id="s1">'
        '<div class="card" data-osd-id="existing">'
        '<div class="wrap"><img class="widget-chart" data-widget-id="w1"></div>'
        "</div></section>"
    )
    out = sanitize_deck_html(html)
    soup = BeautifulSoup(out, "html.parser")
    card = soup.find("div", class_="card")
    wrap = soup.find("div", class_="wrap")
    assert card is not None and card.get("data-osd-id") == "existing"
    assert wrap is not None and not wrap.get("data-osd-id")


def test_widget_chart_avoids_duplicate_osd_id_when_existing_card_uses_same_index():
    """Untagged card before an already-tagged s1-card-1 must not reuse that id."""
    html = (
        '<section class="slide" data-slide-id="s1">'
        '<div class="card untagged">'
        '<div class="wrap"><img class="widget-chart" data-widget-id="w1"></div>'
        "</div>"
        '<div class="card tagged" data-osd-id="s1-card-1">'
        '<div class="wrap"><img class="widget-chart" data-widget-id="w2"></div>'
        "</div></section>"
    )
    out = sanitize_deck_html(html)
    soup = BeautifulSoup(out, "html.parser")
    untagged = soup.find("div", class_="untagged")
    tagged = soup.find("div", class_="tagged")
    assert untagged is not None
    assert tagged is not None and tagged.get("data-osd-id") == "s1-card-1"
    assert untagged.get("data-osd-id") == "s1-card-2"
    osd_ids = [
        el.get("data-osd-id") for el in soup.find_all(attrs={"data-osd-id": True})
    ]
    assert len(osd_ids) == len(set(osd_ids))
