"""Tests for Pydantic domain models in models.py."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from models import (
    DashboardInfo,
    GenerationHistoryRecord,
    GenerationRequest,
    GenerationResult,
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


class TestDashboardInfo:
    def test_defaults(self) -> None:
        d = DashboardInfo(dashboard_id="d1", name="Sales")
        assert d.description == ""
        assert d.widget_count == 0
        assert d.updated_at is None


class TestWidgetInfo:
    def test_defaults(self) -> None:
        w = WidgetInfo(widget_id="w1", title="Revenue", viz_type="bar")
        assert w.columns == []
        assert w.row_count == 0
        assert w.query_result_summary is None
        assert w.capture_status == "pending"


class TestGenerationRequest:
    def test_required_fields(self) -> None:
        r = GenerationRequest(template_id="t1", dashboard_id="d1")
        assert r.user_prompt is None

    def test_with_prompt(self) -> None:
        r = GenerationRequest(
            template_id="t1",
            dashboard_id="d1",
            user_prompt="Focus on Q4",
        )
        assert r.user_prompt == "Focus on Q4"


class TestGenerationResult:
    def test_defaults(self) -> None:
        res = GenerationResult(google_slides_url="https://docs.google.com/x", slide_count=5)
        assert res.warnings == []
        assert res.skipped_widgets == []


class TestGenerationHistoryRecord:
    def test_required_fields(self) -> None:
        created = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
        rec = GenerationHistoryRecord(
            id="h1",
            template_id="t1",
            dashboard_id="d1",
            user_id="u1",
            google_slides_url="https://docs.google.com/x",
            slide_count=3,
            created_at=created,
        )
        assert rec.user_prompt is None
        assert rec.created_at == created

    def test_user_prompt_optional(self) -> None:
        created = datetime.now(timezone.utc)
        rec = GenerationHistoryRecord(
            id="h1",
            template_id="t1",
            dashboard_id="d1",
            user_id="u1",
            user_prompt="hello",
            google_slides_url="https://x",
            slide_count=1,
            created_at=created,
        )
        assert rec.user_prompt == "hello"
