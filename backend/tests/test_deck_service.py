from unittest.mock import MagicMock

import pytest
from bs4 import BeautifulSoup

from models import Deck

from services.deck_service import (
    DeckMemoryRepo,
    DeckService,
    DeckValidationError,
    _inject_widget_chart_srcs,
    _normalize_accent_markers,
    _strip_llm_footer_triplet,
)


def _ok_deck_html() -> str:
    return (
        "<html><head><style>:root{--osd-bg:#000;--osd-text:#fff;}</style></head>"
        "<body>"
        '<section class="slide" data-slide-id="s1" data-osd-id="el-001a"><h1 data-osd-id="el-7a3f">Hi</h1></section>'
        '<section class="slide" data-slide-id="s2" data-osd-id="el-002b"><p data-osd-id="el-2c81">Body</p></section>'
        "</body></html>"
    )


def _tokens():
    return {
        "palette": {"bg": "#000", "text": "#fff", "accent": "#f00", "muted": "#888"},
        "fonts": {"display": "I", "body": "I"},
        "typeScale": {"hero": 200, "title": 88, "body": 36, "caption": 24},
        "spacing": {"padding": 120, "gap": 48},
        "radius": 0,
    }


def test_inject_widget_chart_srcs_matches_data_widget_id_without_widget_chart_class():
    html = (
        '<html><body><img data-widget-id="w1"><img class="widget-chart"></body></html>'
    )
    widget_charts = {
        "w1": "data:image/png;base64,AAA",
        "w2": "data:image/png;base64,BBB",
    }
    out = _inject_widget_chart_srcs(html, widget_charts)
    soup = BeautifulSoup(out, "html.parser")
    imgs = soup.find_all("img")
    assert len(imgs) == 2
    by_widget_id = {img.get("data-widget-id"): img for img in imgs}
    assert by_widget_id["w1"]["src"] == "data:image/png;base64,AAA"
    assert by_widget_id["w2"]["src"] == "data:image/png;base64,BBB"


def test_normalize_accent_markers_converts_double_asterisks():
    html = (
        "<html><head><style>body{}</style></head>"
        "<body><h1>Hello **world** today</h1></body></html>"
    )
    out = _normalize_accent_markers(html)
    assert '<span class="accent">world</span>' in out
    assert ".accent" in out
    assert "var(--osd-accent)" in out


def test_strip_llm_footer_triplet_removes_logo_text_and_page_number():
    html = (
        "<html><body>"
        '<section class="slide" data-layout="content">'
        "<h1>Title</h1>"
        '<img class="deck-logo" src="https://cdn.example/databricks-logo.svg" alt="">'
        "<span>Databricks Inc. — All rights reserved  </span>"
        '<span class="page-number">3</span>'
        "</section>"
        "</body></html>"
    )
    out = _strip_llm_footer_triplet(html)
    soup = BeautifulSoup(out, "html.parser")
    sec = soup.find("section")
    assert sec.find("img") is None
    assert sec.find("span") is None
    assert "Databricks Inc." not in sec.get_text()
    assert sec.find("h1") is not None


def test_strip_llm_footer_triplet_handles_deck_footer_wrapper():
    html = (
        "<html><body>"
        '<section class="slide" data-layout="content"><p>Body</p>'
        '<footer class="deck-footer">'
        '<img class="deck-logo" src="x.png">'
        "<span>Databricks Inc. — All rights reserved</span>"
        "<span>3</span>"
        "</footer>"
        "</section>"
        "</body></html>"
    )
    out = _strip_llm_footer_triplet(html)
    assert "deck-footer" not in out
    assert "<footer" not in out.lower()
    soup = BeautifulSoup(out, "html.parser")
    sec = soup.find("section")
    assert sec.find("footer") is None
    assert sec.find("p") is not None


def test_strip_llm_footer_triplet_preserves_unrelated_imgs():
    html = (
        "<html><body>"
        '<section class="slide" data-layout="two-column">'
        '<div class="col"><img class="widget-chart" src="chart.png"></div>'
        "</section>"
        "</body></html>"
    )
    out = _strip_llm_footer_triplet(html)
    soup = BeautifulSoup(out, "html.parser")
    img = soup.find("img", class_=lambda c: c and "widget-chart" in c)
    assert img is not None
    assert img.get("src") == "chart.png"


def test_strip_llm_footer_triplet_preserves_logo_in_cover():
    html = (
        "<html><body>"
        '<section class="slide" data-layout="title">'
        '<div class="cover-content">'
        '<img class="cover-logo" src="https://cdn.example/databricks-logo-wide.svg">'
        "</div>"
        "</section>"
        "</body></html>"
    )
    out = _strip_llm_footer_triplet(html)
    soup = BeautifulSoup(out, "html.parser")
    img = soup.find("img", class_=lambda c: c and "cover-logo" in c)
    assert img is not None
    assert "databricks-logo" in (img.get("src") or "").lower()


def test_strip_llm_footer_triplet_removes_closing_foot_wrapper():
    html = (
        "<html><body>"
        '<section class="slide" data-layout="closing">'
        '<div class="closing-content"><p>Thanks</p></div>'
        '<div class="closing-foot">'
        '<img alt="Databricks" src="/databricks-logo-light.svg">'
        "<span>Databricks Inc. — Custom team line</span>"
        "</div>"
        "</section>"
        "</body></html>"
    )
    out = _strip_llm_footer_triplet(html)
    soup = BeautifulSoup(out, "html.parser")
    sec = soup.find("section")
    assert sec.find(class_="closing-foot") is None
    assert sec.find(class_="closing-content") is not None
    assert sec.find("p") is not None


def test_strip_llm_footer_triplet_removes_databricks_inc_variants():
    html = (
        "<html><body>"
        '<section class="slide" data-layout="content"><span>Databricks Inc. — All rights reserved</span></section>'
        '<section class="slide" data-layout="content"><span>Databricks Inc. — Support Team · 2024</span></section>'
        "</body></html>"
    )
    out = _strip_llm_footer_triplet(html)
    assert "Databricks Inc." not in out


def test_strip_llm_footer_triplet_keeps_cover_logo():
    html = (
        "<html><body>"
        '<section class="slide" data-layout="title">'
        '<div class="cover">'
        '<img class="cover-logo" src="/databricks-logo-dark.svg">'
        "</div>"
        "</section>"
        "</body></html>"
    )
    out = _strip_llm_footer_triplet(html)
    soup = BeautifulSoup(out, "html.parser")
    img = soup.find("img", class_=lambda c: c and "cover-logo" in c)
    assert img is not None
    assert (img.get("src") or "").endswith("databricks-logo-dark.svg")


def test_normalize_accent_markers_skips_style_and_script_text():
    html = (
        "<html><head><style>.x::before{content:'**no**';}</style>"
        "</head><body><p>x **yes** y</p>"
        "<script>const s = '**no**'</script></body></html>"
    )
    out = _normalize_accent_markers(html)
    assert '<span class="accent">yes</span>' in out
    assert "**no**" in out  # left inside style & script


def test_generate_outline_parses_json():
    llm = MagicMock()
    llm.generate_deck_outline = MagicMock(
        return_value='{"slides": [{"layout": "title", "title": "Cover", "summary": "Intro", "notes": ""}]}'
    )
    svc = DeckService(llm=llm, repo=MagicMock())
    out = svc.generate_outline(
        tokens={},
        theme_markdown="",
        widgets=[],
        user_prompt=None,
    )
    assert len(out) == 1
    assert out[0]["layout"] == "title"
    assert out[0]["title"] == "Cover"


def test_generate_outline_passes_reference_doc_to_llm():
    llm = MagicMock()
    llm.generate_deck_outline = MagicMock(
        return_value='{"slides": [{"layout": "title", "title": "A", "summary": "B", "notes": ""}]}'
    )
    svc = DeckService(llm=llm, repo=MagicMock())
    svc.generate_outline(
        tokens={},
        theme_markdown="tm",
        widgets=[],
        user_prompt="p",
        reference_doc="doc body",
        reference_doc_name="one.md",
    )
    llm.generate_deck_outline.assert_called_once()
    call_kw = llm.generate_deck_outline.call_args.kwargs
    assert call_kw["reference_doc"] == "doc body"
    assert call_kw["reference_doc_name"] == "one.md"


def test_update_gslides_link_persists_file_id_and_url():
    repo = DeckMemoryRepo()
    deck = Deck(
        id="d-gslides",
        user_id="u1",
        template_id="t1",
        genie_space_id="dash1",
        google_slides_template_id="",
        html_doc="<html><body></body></html>",
        design_tokens={},
        theme_markdown="",
    )
    repo.insert_deck(deck)
    llm = MagicMock()
    svc = DeckService(llm=llm, repo=repo)
    svc.update_gslides_link(
        "d-gslides", "u1", "presABC", "https://docs.example/d/presABC"
    )
    loaded = repo.get_deck("d-gslides", "u1")
    assert loaded is not None
    assert loaded.gslides_file_id == "presABC"
    assert loaded.gslides_url == "https://docs.example/d/presABC"


def test_generate_outline_raises_on_bad_json():
    llm = MagicMock()
    llm.generate_deck_outline = MagicMock(return_value="not json")
    svc = DeckService(llm=llm, repo=MagicMock())
    with pytest.raises(DeckValidationError, match="outline JSON parse"):
        svc.generate_outline(
            tokens={},
            theme_markdown="",
            widgets=[],
            user_prompt=None,
        )


def _drifted_two_slide_deck_html() -> str:
    """Monolithic-style deck where slide 2 has wrong data-layout vs outline."""
    return (
        "<html><head><style>:root{--osd-bg:#000;--osd-text:#fff;}</style></head>"
        "<body>"
        '<section class="slide" data-layout="title" data-slide-id="s1" data-osd-id="el-001a">'
        '<h1 data-osd-id="el-h1">Cover</h1></section>'
        '<section class="slide" data-layout="big-number" data-slide-id="s2" data-osd-id="el-002b">'
        '<p data-osd-id="el-p1">Drift</p></section>'
        "</body></html>"
    )


def test_generate_deck_reconciles_drifted_layouts_with_outline():
    llm = MagicMock()
    llm.generate_deck_html = MagicMock(return_value=_drifted_two_slide_deck_html())
    fixed_slide = (
        '<section class="slide" data-layout="agenda" data-slide-id="s2" data-osd-id="el-002b">'
        '<ul data-osd-id="el-ul1"><li data-osd-id="el-li1">Item</li></ul></section>'
    )
    llm.regenerate_slide_section = MagicMock(return_value=fixed_slide)
    repo = MagicMock()
    svc = DeckService(llm=llm, repo=repo)
    outline = [
        {"layout": "title", "title": "Cover", "summary": "Hello", "notes": ""},
        {"layout": "agenda", "title": "Agenda", "summary": "Topics", "notes": ""},
    ]
    deck = svc.generate_deck(
        user_id="u1",
        template_id="t1",
        genie_space_id="d1",
        google_slides_template_id="gs-tpl-1",
        user_prompt=None,
        tokens=_tokens(),
        theme_markdown="tm",
        widgets=[],
        outline=outline,
        questions=["What is revenue?"],
    )
    assert deck.genie_space_id == "d1"
    assert deck.questions == ["What is revenue?"]
    llm.generate_deck_html.assert_called_once()
    call_kw = llm.generate_deck_html.call_args.kwargs
    assert call_kw.get("outline") == outline

    llm.regenerate_slide_section.assert_called_once()
    regen_kw = llm.regenerate_slide_section.call_args.kwargs
    assert regen_kw["tokens"] == _tokens()
    assert regen_kw["theme_markdown"] == "tm"
    want_feedback = (
        'This slide MUST have data-layout="agenda" per the outline. '
        'Outline: layout=agenda, title="Agenda", '
        'summary="Topics". '
        "Rewrite to match that layout shape exactly. "
        'Preserve the existing data-slide-id="s2" '
        'and data-osd-id="el-002b" attributes. '
        "Use the same CSS classes as the rest of the deck (deck-footer, deck-logo, "
        "slide-topbar, eyebrow, accent, etc.)."
    )
    assert regen_kw["feedback"] == want_feedback
    assert 'data-layout="big-number"' in regen_kw["slide_outer_html"]

    assert 'data-layout="agenda"' in deck.html_doc
    assert "Item" in deck.html_doc


def test_generate_deck_creates_deck_and_revision():
    llm = MagicMock()
    llm.generate_deck_html = MagicMock(side_effect=lambda **kw: _ok_deck_html())
    repo = MagicMock()
    svc = DeckService(llm=llm, repo=repo)

    deck = svc.generate_deck(
        user_id="u1",
        template_id="t1",
        genie_space_id="d1",
        google_slides_template_id="gs-tpl-1",
        user_prompt=None,
        tokens=_tokens(),
        theme_markdown="Mono.",
        widgets=[],
    )
    assert deck.user_id == "u1"
    assert deck.google_slides_template_id == "gs-tpl-1"
    assert "<section" in deck.html_doc
    repo.insert_deck.assert_called_once()
    repo.insert_revision.assert_called_once()


def test_generate_deck_rejects_duplicate_data_osd_id():
    bad = (
        "<html><body>"
        '<section class="slide" data-slide-id="s1" data-osd-id="el-001a"><h1 data-osd-id="el-DUP1">A</h1></section>'
        '<section class="slide" data-slide-id="s2" data-osd-id="el-001a"><p data-osd-id="el-DUP1">B</p></section>'
        "</body></html>"
    )
    llm = MagicMock()
    llm.generate_deck_html = MagicMock(side_effect=lambda **kw: bad)
    repo = MagicMock()
    svc = DeckService(llm=llm, repo=repo)
    with pytest.raises(DeckValidationError):
        svc.generate_deck(
            user_id="u1",
            template_id="t1",
            genie_space_id="d1",
            google_slides_template_id="gs-tpl-1",
            user_prompt=None,
            tokens=_tokens(),
            theme_markdown="",
            widgets=[],
        )


def test_save_comment_inserts_marker_and_revision():
    llm = MagicMock()
    repo = MagicMock()
    from models import Deck

    deck0 = Deck(
        id="d1",
        user_id="u1",
        template_id="t1",
        genie_space_id="dash",
        google_slides_template_id="gs",
        user_prompt=None,
        html_doc=_ok_deck_html(),
        design_tokens=_tokens(),
        theme_markdown="",
        status="draft",
    )
    repo.get_deck.return_value = deck0
    repo.count_revisions.return_value = 1
    svc = DeckService(llm=llm, repo=repo)
    deck, rev_no = svc.save_comment(
        deck_id="d1", user_id="u1", target_id="el-7a3f", note="redder"
    )
    assert "osd-comment" in deck.html_doc
    repo.update_deck_html.assert_called_once()
    repo.insert_revision.assert_called_once()


def test_apply_comment_replaces_subtree_atomic_failure_restores():
    bad_html = '<html><body><h1 data-osd-id="el-7a3f"><!--osd-comment id="c-aaaa" target="el-7a3f" ts="2026-01-01T00:00:00Z" note="x"-->A</h1></body></html>'
    llm = MagicMock()
    llm.rewrite_element = MagicMock(side_effect=lambda **kw: "<not even valid html")
    from models import Deck

    deck0 = Deck(
        id="d1",
        user_id="u1",
        template_id="t1",
        genie_space_id="dash",
        google_slides_template_id="gs",
        user_prompt=None,
        html_doc=bad_html,
        design_tokens=_tokens(),
        theme_markdown="",
        status="draft",
    )
    repo = MagicMock()
    repo.get_deck.return_value = deck0
    repo.count_revisions.return_value = 2
    svc = DeckService(llm=llm, repo=repo)
    with pytest.raises(DeckValidationError):
        svc.apply_comment(deck_id="d1", user_id="u1", comment_id="c-aaaa")
    repo.update_deck_html.assert_not_called()
    repo.insert_revision.assert_not_called()


def test_regenerate_slide_replaces_section_and_records_revision():
    llm = MagicMock()
    llm.regenerate_slide_section = MagicMock(
        return_value=(
            '<section class="slide" data-slide-id="s1" data-layout="content" '
            'data-osd-id="el-001a">'
            '<h1 data-osd-id="el-7a3f">Regenerated</h1></section>'
        )
    )
    from models import Deck

    deck0 = Deck(
        id="d1",
        user_id="u1",
        template_id="t1",
        genie_space_id="dash",
        google_slides_template_id="gs",
        user_prompt=None,
        html_doc=_ok_deck_html(),
        design_tokens=_tokens(),
        theme_markdown="",
        status="draft",
    )
    repo = MagicMock()
    repo.get_deck.return_value = deck0
    repo.count_revisions.return_value = 2
    svc = DeckService(llm=llm, repo=repo)
    deck, rev_no = svc.regenerate_slide(
        deck_id="d1", user_id="u1", slide_id="s1", feedback="shorter"
    )
    assert rev_no == 3
    assert "Regenerated" in deck.html_doc
    assert "Hi" not in deck.html_doc
    assert "Body" in deck.html_doc
    kw = llm.regenerate_slide_section.call_args.kwargs
    assert kw["feedback"] == "shorter"
    repo.update_deck_html.assert_called_once()
    repo.insert_revision.assert_called_once()
    assert repo.insert_revision.call_args[0][0].trigger == "regenerate_slide"


def test_revision_pruning_cap_20():
    llm = MagicMock()
    repo = MagicMock()
    repo.count_revisions.return_value = 21
    svc = DeckService(llm=llm, repo=repo)
    svc._prune_revisions(deck_id="d1")
    repo.delete_oldest_non_genesis_revision.assert_called_once_with("d1")


def test_uc_repo_insert_deck_runs_insert_sql():
    from models import Deck
    from services.deck_service import DeckUCRepo

    sql_client = MagicMock()
    repo = DeckUCRepo(sql_client=sql_client, catalog="cat", schema="sch")
    deck = Deck(
        id="d1",
        user_id="u1",
        template_id="t1",
        genie_space_id="dash1",
        google_slides_template_id="gs-tpl",
        user_prompt=None,
        html_doc="<html></html>",
        design_tokens={"palette": {"bg": "#000"}},
        theme_markdown="",
        status="draft",
    )
    repo.insert_deck(deck)
    assert sql_client.execute.called
    args, _ = sql_client.execute.call_args
    sql = args[0]
    assert "INSERT INTO" in sql
    assert "decks" in sql
    assert "'d1'" in sql
    assert "'gs-tpl'" in sql


def test_uc_repo_get_deck_filters_user_id():
    from services.deck_service import DeckUCRepo

    sql_client = MagicMock()
    sql_client.fetchone.return_value = None
    repo = DeckUCRepo(sql_client=sql_client, catalog="cat", schema="sch")
    repo.get_deck("d1", "u1")
    sql_client.fetchone.assert_called_once()
    args, _ = sql_client.fetchone.call_args
    sql = args[0]
    assert "id = 'd1'" in sql
    assert "user_id = 'u1'" in sql


def test_uc_repo_q_escapes_backslash_and_quote():
    """Defensive: spark.sql.parser.escapedStringLiterals=false honors C-style escapes,
    so backslashes must be doubled before doubling quotes. Otherwise `\\'` becomes
    `\\''` which closes the literal early."""
    from services.deck_service import DeckUCRepo

    # Backslash before quote — the dangerous case
    assert DeckUCRepo._q("\\'") == "\\\\''"
    # Plain quote still doubles
    assert DeckUCRepo._q("a'b") == "a''b"
    # Backslash alone doubles
    assert DeckUCRepo._q("a\\b") == "a\\\\b"
    # No special chars — passthrough
    assert DeckUCRepo._q("hello") == "hello"


def test_audit_deck_parses_json_issues():
    llm = MagicMock()
    llm.audit_deck = MagicMock(
        return_value='{"issues": [{"slide_id": "s1", "severity": "P1", "message": "x", "fix_hint": "y"}]}'
    )
    from models import Deck

    deck = Deck(
        id="d-audit",
        user_id="u1",
        template_id="t",
        genie_space_id="d",
        google_slides_template_id="",
        html_doc=_ok_deck_html(),
        design_tokens=_tokens(),
        theme_markdown="",
    )
    repo = MagicMock()
    repo.get_deck.return_value = deck
    svc = DeckService(llm=llm, repo=repo)
    issues = svc.audit_deck(deck_id="d-audit", user_id="u1")
    assert len(issues) == 1
    assert issues[0]["slide_id"] == "s1"
    assert issues[0]["severity"] == "P1"
    llm.audit_deck.assert_called_once()


def test_audit_and_fix_regenerates_p1_slide():
    from models import Deck

    repo = MagicMock()
    deck_html = _ok_deck_html()
    deck = Deck(
        id="d-fix",
        user_id="u1",
        template_id="t",
        genie_space_id="d",
        google_slides_template_id="",
        html_doc=deck_html,
        design_tokens=_tokens(),
        theme_markdown="",
    )
    repo.get_deck.return_value = deck
    repo.count_revisions.return_value = 2

    llm = MagicMock()
    llm.audit_deck = MagicMock(
        return_value='{"issues": [{"slide_id": "s1", "severity": "P1", "message": "bad", "fix_hint": "improve"}]}'
    )
    llm.regenerate_slide_section = MagicMock(
        return_value=(
            '<section class="slide" data-slide-id="s1" data-osd-id="el-root-new" '
            'data-layout="content"><p data-osd-id="el-p-new">Fixed</p></section>'
        )
    )
    svc = DeckService(llm=llm, repo=repo)
    out, issues = svc.audit_and_fix_deck(deck_id="d-fix", user_id="u1")
    assert len(issues) == 1
    assert llm.regenerate_slide_section.call_count == 1
    assert "Fixed" in out.html_doc
    repo.update_deck_html.assert_called()
