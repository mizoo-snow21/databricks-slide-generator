"""Tests for Pydantic domain models in models.py."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from models import (
    Deck,
    DesignTokens,
    GenerationRequest,
    GenerationResult,
    PendingComment,
    PptxExtractResult,
    Template,
    TemplateBrand,
    TemplateCreate,
    TemplateGuidelines,
    WidgetInfo,
)


class TestTemplateBrand:
    def test_defaults(self) -> None:
        b = TemplateBrand()
        assert b.primary == "#333333"
        assert b.secondary == "#666666"
        assert b.accent == "#0066CC"
        assert b.text_dark == "#202124"
        assert b.text_light == "#FFFFFF"
        assert b.font == "Noto Sans JP"

    def test_custom_values(self) -> None:
        b = TemplateBrand(primary="#000000", font="Roboto")
        assert b.primary == "#000000"
        assert b.font == "Roboto"
        assert b.secondary == "#666666"

    def test_invalid_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TemplateBrand.model_validate({"primary": {}})  # type: ignore[arg-type]


class TestTemplateGuidelines:
    def test_chart_preference_required(self) -> None:
        with pytest.raises(ValidationError) as exc:
            TemplateGuidelines()
        assert "chart_preference" in str(exc.value).lower()

    def test_defaults_when_chart_preference_set(self) -> None:
        g = TemplateGuidelines(chart_preference="bar_first")
        assert g.total_slides_min == 6
        assert g.total_slides_max == 12
        assert g.structure_hint == "Overview → Data detail → Insights → Next actions"
        assert g.preferred_layouts == [
            "title",
            "content_basic",
            "content_2col",
            "title_only",
            "closing",
        ]
        assert g.style_notes == "Concise. One message per slide."
        assert g.must_include == ["title", "closing"]
        assert g.chart_preference == "bar_first"

    def test_total_slides_must_be_int(self) -> None:
        with pytest.raises(ValidationError):
            TemplateGuidelines.model_validate(
                {"chart_preference": "x", "total_slides_min": "six"}  # type: ignore[dict-item]
            )


class TestTemplateCreate:
    def test_requires_name_and_google_slides_template_id(self) -> None:
        with pytest.raises(ValidationError):
            TemplateCreate(google_slides_template_id="abc")  # type: ignore[call-arg]
        with pytest.raises(ValidationError):
            TemplateCreate(name="n")  # type: ignore[call-arg]

    def test_defaults(self) -> None:
        t = TemplateCreate(
            name="Corp Deck",
            google_slides_template_id="abc123",
        )
        assert t.description == ""
        assert t.theme == "light"
        assert isinstance(t.brand, TemplateBrand)
        assert t.brand.font == "Noto Sans JP"
        assert isinstance(t.guidelines, TemplateGuidelines)
        assert t.guidelines.chart_preference == "auto"
        assert t.preset_id is None
        assert t.pptx_file_path is None
        assert t.pptx_upload_id is None


class TestPptxExtractResult:
    def test_defaults(self) -> None:
        tokens = DesignTokens(
            palette={"bg": "#fff", "text": "#000", "accent": "#f00", "muted": "#888"},
            fonts={"display": "'X', sans-serif", "body": "'X', sans-serif"},
            typeScale={"hero": 1, "title": 2, "body": 3, "caption": 4},
            spacing={"padding": 1, "gap": 2},
        )
        r = PptxExtractResult(upload_id="u1", suggested_name="My Deck", tokens=tokens)
        assert r.theme_markdown == ""


class TestTemplate:
    def test_extends_template_create(self) -> None:
        tpl = Template(
            id="tpl-1",
            name="Corp Deck",
            google_slides_template_id="abc123",
        )
        assert isinstance(tpl, TemplateCreate)
        assert tpl.id == "tpl-1"
        assert tpl.thumbnail_url is None
        assert tpl.created_by == ""
        assert tpl.created_at is None
        assert tpl.updated_at is None

    def test_template_optional_metadata(self) -> None:
        now = datetime.now(timezone.utc)
        tpl = Template(
            id="tpl-1",
            name="n",
            google_slides_template_id="g",
            thumbnail_url="https://example.com/t.png",
            created_by="user@example.com",
            created_at=now,
            updated_at=now,
        )
        assert tpl.thumbnail_url == "https://example.com/t.png"
        assert tpl.created_by == "user@example.com"
        assert tpl.created_at == now
        assert tpl.updated_at == now


class TestWidgetInfo:
    def test_defaults(self) -> None:
        w = WidgetInfo(widget_id="w1", title="Revenue", viz_type="bar")
        assert w.columns == []
        assert w.row_count == 0
        assert w.query_result_summary is None
        assert w.capture_status == "pending"
        assert w.sql_text is None
        assert w.lakeview_spec is None


class TestGenerationRequest:
    def test_required_fields(self) -> None:
        r = GenerationRequest(template_id="t1", genie_space_id="d1")
        assert r.user_prompt is None
        assert r.high_quality is True

    def test_with_prompt(self) -> None:
        r = GenerationRequest(
            template_id="t1",
            genie_space_id="d1",
            user_prompt="Focus on Q4",
        )
        assert r.user_prompt == "Focus on Q4"

    def test_questions_default_empty(self) -> None:
        r = GenerationRequest(template_id="t1", genie_space_id="d1")
        assert r.questions == []
        r2 = GenerationRequest(
            template_id="t1",
            genie_space_id="d1",
            questions=["What is revenue?"],
        )
        assert r2.questions == ["What is revenue?"]


class TestGenerationResult:
    def test_defaults(self) -> None:
        res = GenerationResult(slides_url="https://docs.google.com/x", slide_count=5)
        assert res.warnings == []
        assert res.skipped_widgets == []


def test_design_tokens_palette_required() -> None:
    tokens = DesignTokens(
        palette={"bg": "#000", "text": "#fff", "accent": "#f00", "muted": "#888"},
        fonts={"display": "Inter", "body": "Inter"},
        typeScale={"hero": 200, "title": 88, "body": 36, "caption": 24},
        spacing={"padding": 120, "gap": 48},
        radius=0,
    )
    assert tokens.palette["accent"] == "#f00"
    assert tokens.typeScale["hero"] == 200


def test_template_create_accepts_tokens_and_theme_markdown() -> None:
    t = TemplateCreate(
        name="QBR Noir",
        google_slides_template_id="abc",
        tokens=DesignTokens(
            palette={
                "bg": "#0a0a0a",
                "text": "#fff",
                "accent": "#f00",
                "muted": "#888",
            },
            fonts={"display": "Inter", "body": "Inter"},
            typeScale={"hero": 200, "title": 88, "body": 36, "caption": 24},
            spacing={"padding": 120, "gap": 48},
            radius=0,
        ),
        theme_markdown="Editorial monochrome with one hot accent.",
    )
    assert t.theme_markdown.startswith("Editorial")
    assert t.tokens.radius == 0


def test_deck_status_default() -> None:
    d = Deck(
        id="d1",
        user_id="u",
        template_id="t",
        genie_space_id="dash",
        html_doc="<html></html>",
        design_tokens={},
        theme_markdown="",
        google_slides_template_id="gs-abc",
    )
    assert d.status == "draft"
    assert d.google_slides_template_id == "gs-abc"
    assert d.chart_warnings == []


def test_deck_snapshots_google_slides_template_id() -> None:
    d = Deck(
        id="d1",
        user_id="u",
        template_id="t",
        genie_space_id="dash",
        html_doc="<html></html>",
        design_tokens={},
        theme_markdown="",
        google_slides_template_id="gs-original",
    )
    assert d.google_slides_template_id == "gs-original"


def test_pending_comment_shape() -> None:
    c = PendingComment(
        id="c-9b2e",
        target_id="el-7a3f",
        note="redder",
        ts="2026-05-07T12:00:00Z",
    )
    assert c.id.startswith("c-")
