from io import BytesIO

from pptx import Presentation

from services.pptx_theme_extractor import extract_design_tokens_from_pptx


def test_extracts_from_minimal_pptx() -> None:
    prs = Presentation()
    buf = BytesIO()
    prs.save(buf)
    tokens = extract_design_tokens_from_pptx(buf.getvalue())
    assert tokens["palette"]["bg"].startswith("#")
    assert tokens["palette"]["text"].startswith("#")
    assert tokens["palette"]["accent"].startswith("#")
    assert tokens["palette"]["muted"].startswith("#")
    assert "'" in tokens["fonts"]["display"]
    assert tokens["typeScale"]["hero"] == 180
