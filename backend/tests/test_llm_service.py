"""Tests for LLM slide composition (prompt building and response parsing)."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models import TemplateGuidelines, WidgetInfo
from services.llm_service import (
    AVAILABLE_LAYOUTS,
    LLMService,
    SLIDE_AUTHORING_RULES,
    build_prompt,
)


def _sample_widgets() -> list[WidgetInfo]:
    return [
        WidgetInfo(
            widget_id="w1",
            title="Revenue",
            viz_type="bar_chart",
            columns=["month", "revenue"],
            row_count=12,
            query_result_summary="Peak in Oct: $1.5M",
        ),
        WidgetInfo(
            widget_id="w2",
            title="Users",
            viz_type="counter",
            columns=["count"],
            row_count=1,
        ),
    ]


def _sample_guidelines() -> TemplateGuidelines:
    return TemplateGuidelines(chart_preference="line_first")


class TestBuildPrompt:
    def test_contains_all_sections(self) -> None:
        prompt = build_prompt(
            _sample_widgets(),
            _sample_guidelines(),
            "Q4 Executive Dashboard",
            user_prompt="Emphasize growth",
        )
        assert "Q4 Executive Dashboard" in prompt
        assert "Widgets" in prompt or "widget" in prompt.lower()
        assert "Template guidelines" in prompt or "guidelines" in prompt.lower()
        assert AVAILABLE_LAYOUTS.strip() in prompt or "two-column" in prompt
        assert "Instructions" in prompt
        assert "line_first" in prompt
        assert "two-column" in prompt or "**content**" in prompt

    def test_without_user_prompt_omits_user_direction(self) -> None:
        prompt = build_prompt(
            _sample_widgets(),
            _sample_guidelines(),
            "Sales Overview",
            user_prompt=None,
        )
        assert "User direction" not in prompt

    def test_includes_widget_summaries(self) -> None:
        prompt = build_prompt(
            _sample_widgets(),
            _sample_guidelines(),
            "Dash",
        )
        assert "w1" in prompt
        assert "Revenue" in prompt
        assert "bar_chart" in prompt
        assert "month" in prompt and "revenue" in prompt
        assert "12" in prompt
        assert "Peak in Oct" in prompt
        assert "w2" in prompt
        assert "counter" in prompt


class TestParseResponse:
    def test_extracts_json_from_markdown_code_block(self) -> None:
        raw = """Here is the spec:
```json
[{"layout": "title", "title": "Hello"}]
```
"""
        service = LLMService()
        out = service._parse_response(raw)
        assert out == [{"layout": "title", "title": "Hello"}]

    def test_parses_raw_json_array(self) -> None:
        raw = '[{"a": 1}, {"b": 2}]'
        service = LLMService()
        assert service._parse_response(raw) == [{"a": 1}, {"b": 2}]

    def test_invalid_json_raises_value_error(self) -> None:
        service = LLMService()
        with pytest.raises(ValueError, match="JSON|parse"):
            service._parse_response("not json at all")

    def test_non_array_json_raises_value_error(self) -> None:
        service = LLMService()
        with pytest.raises(ValueError, match="array"):
            service._parse_response('{"slides": []}')


class TestComposeSlides:
    @patch("httpx.AsyncClient")
    def test_calls_serving_endpoint_and_returns_parsed_list(
        self,
        mock_async_client_cls: MagicMock,
    ) -> None:
        class FakeConfig:
            host = "https://test.databricks.com"

            def authenticate(self) -> dict:
                return {"Authorization": "Bearer fake-token"}

        class FakeWorkspaceClient:
            def __init__(self) -> None:
                self.config = FakeConfig()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '[{"layout": "closing"}]'}}],
        }

        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_response)

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_async_client_cls.return_value = mock_cm

        client = FakeWorkspaceClient()
        service = LLMService(workspace_client=client)

        result = asyncio.run(
            service.compose_slides(
                _sample_widgets(),
                _sample_guidelines(),
                "My Dashboard",
                user_prompt="Keep it short",
            )
        )

        assert result == [{"layout": "closing"}]
        mock_http.post.assert_awaited_once()
        call_kwargs = mock_http.post.await_args
        assert call_kwargs is not None
        url = call_kwargs.args[0] if call_kwargs.args else call_kwargs.kwargs.get("url")
        assert url == (
            "https://test.databricks.com/serving-endpoints/"
            "databricks-claude-sonnet-4-6/invocations"
        )
        payload = call_kwargs.kwargs.get("json") or {}
        assert payload["max_tokens"] == 4096
        assert payload["temperature"] == 0.3
        messages = payload["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        body = messages[0]["content"]
        assert "My Dashboard" in body
        assert "User direction" in body
        assert "Keep it short" in body

    def test_compose_without_client_raises(self) -> None:
        service = LLMService(workspace_client=None)
        with pytest.raises(RuntimeError, match="Workspace client"):
            asyncio.run(
                service.compose_slides(
                    _sample_widgets(),
                    _sample_guidelines(),
                    "X",
                )
            )

    @patch("httpx.AsyncClient")
    def test_compose_raises_when_endpoint_returns_no_choices(
        self,
        mock_async_client_cls: MagicMock,
    ) -> None:
        class FakeConfig:
            host = "https://test.databricks.com"

            def authenticate(self) -> dict:
                return {"Authorization": "Bearer fake-token"}

        class FakeWorkspaceClient:
            def __init__(self) -> None:
                self.config = FakeConfig()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"choices": []}

        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_response)

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_async_client_cls.return_value = mock_cm

        service = LLMService(workspace_client=FakeWorkspaceClient())
        with pytest.raises(ValueError, match="LLM endpoint returned no choices"):
            asyncio.run(
                service.compose_slides(
                    _sample_widgets(),
                    _sample_guidelines(),
                    "Dash",
                )
            )


def test_slide_authoring_rules_present() -> None:
    """The open-slide slide-authoring rules must be embedded in the system prompt."""
    assert "1920" in SLIDE_AUTHORING_RULES
    assert "1080" in SLIDE_AUTHORING_RULES
    assert (
        "vertical" in SLIDE_AUTHORING_RULES.lower()
        or "budget" in SLIDE_AUTHORING_RULES.lower()
    )


def test_slide_authoring_rules_include_house_style() -> None:
    """House-style guidance covers Databricks default and consulting override."""
    assert "#f9f7f5" in SLIDE_AUTHORING_RULES
    assert "DM Mono" in SLIDE_AUTHORING_RULES
    assert "12-column" in SLIDE_AUTHORING_RULES
    assert "Meiryo" in SLIDE_AUTHORING_RULES
    assert "メイリオ" in SLIDE_AUTHORING_RULES
    assert "McKinsey" in SLIDE_AUTHORING_RULES
    assert "never render the McKinsey logo" in SLIDE_AUTHORING_RULES


def test_build_deck_html_prompt_includes_tokens_and_theme() -> None:
    svc = LLMService()
    prompt = svc._build_deck_html_prompt(
        tokens={
            "palette": {
                "bg": "#000",
                "text": "#fff",
                "accent": "#f00",
                "muted": "#888",
            },
            "fonts": {"display": "Inter", "body": "Inter"},
            "typeScale": {"hero": 200, "title": 88, "body": 36, "caption": 24},
            "spacing": {"padding": 120, "gap": 48},
            "radius": 0,
        },
        theme_markdown="Editorial monochrome with one hot accent.",
        widgets=[],
        user_prompt="Q4 review focused on NA region",
    )
    assert "Editorial monochrome" in prompt
    assert "--osd-bg" in prompt or "#000" in prompt
    assert "Q4 review" in prompt
    assert "data-osd-id" in prompt
    assert "data-source-widget-id" in prompt


def test_build_rewrite_element_prompt_includes_target_and_note() -> None:
    svc = LLMService()
    prompt = svc._build_rewrite_element_prompt(
        target_outer_html=(
            '<h1 data-osd-id="el-7a3f"><!--osd-comment id="c-1aaa" target="el-7a3f" ts="now" note="redder"-->X</h1>'
        ),
        slide_excerpt='<section data-slide-id="s1">...</section>',
        tokens={
            "palette": {
                "bg": "#000",
                "text": "#fff",
                "accent": "#f00",
                "muted": "#888",
            },
            "fonts": {"display": "I", "body": "I"},
            "typeScale": {"hero": 200, "title": 88, "body": 36, "caption": 24},
            "spacing": {"padding": 120, "gap": 48},
            "radius": 0,
        },
        theme_markdown="Mono.",
        note="make the headline larger and bolder",
    )
    assert "el-7a3f" in prompt
    assert "make the headline larger" in prompt
    lowered = prompt.lower()
    assert (
        "single html element" in lowered
        or "one root element" in lowered
        or "one html element" in lowered
    )


def test_build_add_slide_prompt_requests_section_root() -> None:
    svc = LLMService()
    prompt = svc._build_add_slide_prompt(
        deck_html='<html><body><section data-slide-id="s1">A</section></body></html>',
        tokens={
            "palette": {
                "bg": "#000",
                "text": "#fff",
                "accent": "#f00",
                "muted": "#888",
            },
            "fonts": {"display": "I", "body": "I"},
            "typeScale": {"hero": 200, "title": 88, "body": 36, "caption": 24},
            "spacing": {"padding": 120, "gap": 48},
            "radius": 0,
        },
        theme_markdown="Mono.",
        user_prompt="add a closing slide with a call to action",
    )
    assert "section" in prompt.lower()
    assert "data-slide-id" in prompt
    assert "data-osd-id" in prompt
    assert "call to action" in prompt


def test_build_regenerate_slide_prompt_includes_slide_and_feedback() -> None:
    svc = LLMService()
    slide_html = '<section class="slide" data-slide-id="s1" data-osd-id="r"><h1>Old</h1></section>'
    deck = "<html><body>" + slide_html + "</body></html>"
    prompt = svc._build_regenerate_slide_prompt(
        _deck_html=deck,
        slide_outer_html=slide_html,
        tokens={
            "palette": {
                "bg": "#000",
                "text": "#fff",
                "accent": "#f00",
                "muted": "#888",
            },
            "fonts": {"display": "I", "body": "I"},
            "typeScale": {"hero": 200, "title": 88, "body": 36, "caption": 24},
            "spacing": {"padding": 120, "gap": 48},
            "radius": 0,
        },
        theme_markdown="Brand voice",
        feedback="use stat-row layout",
    )
    assert "Brand voice" in prompt
    assert "use stat-row layout" in prompt
    assert "Old" in prompt or slide_html in prompt
    assert "NON-NEGOTIABLE" in prompt


def test_build_html_to_spec_prompt_describes_layouts() -> None:
    svc = LLMService()
    prompt = svc._build_html_to_spec_prompt(
        deck_html='<html><body><section data-slide-id="s1"><h1>Title</h1></section></body></html>',
    )
    assert "create-from-spec" in prompt or "layout" in prompt.lower()
    for key in (
        "agenda",
        "stat-row",
        "two-column",
        "card-left",
        "card-full",
        "callout",
        "big-number",
    ):
        assert key in prompt


def test_html_to_spec_prompt_closing_layout_and_reminder() -> None:
    svc = LLMService()
    prompt = svc._build_html_to_spec_prompt(deck_html="<html><body></body></html>")
    assert "**closing**" in AVAILABLE_LAYOUTS or "closing" in AVAILABLE_LAYOUTS
    assert (
        "no content fields"
        not in AVAILABLE_LAYOUTS.split("**closing**")[-1].split("**blank**")[0]
    )
    assert "fields: `title`" in AVAILABLE_LAYOUTS and "closing" in AVAILABLE_LAYOUTS
    assert "For closing slides specifically" in prompt
    assert "Do NOT leave closing slides with empty content" in prompt


def test_build_deck_html_prompt_includes_outline_block() -> None:
    svc = LLMService()
    prompt = svc._build_deck_html_prompt(
        tokens={
            "palette": {
                "bg": "#000",
                "text": "#fff",
                "accent": "#f00",
                "muted": "#888",
            },
            "fonts": {"display": "I", "body": "I"},
            "typeScale": {"hero": 200, "title": 88, "body": 36, "caption": 24},
            "spacing": {"padding": 120, "gap": 48},
            "radius": 0,
        },
        theme_markdown="Theme.",
        widgets=[],
        user_prompt="Go",
        widget_chart_ids=[],
        outline=[
            {"layout": "title", "title": "Hello", "summary": "World", "notes": "sp"}
        ],
    )
    assert "## Required outline" in prompt
    assert "[layout=title]" in prompt
    assert "Hello" in prompt
    assert "Notes: sp" in prompt


def test_build_deck_html_prompt_omits_outline_block_when_none() -> None:
    svc = LLMService()
    prompt = svc._build_deck_html_prompt(
        tokens={
            "palette": {
                "bg": "#000",
                "text": "#fff",
                "accent": "#f00",
                "muted": "#888",
            },
            "fonts": {"display": "I", "body": "I"},
            "typeScale": {"hero": 200, "title": 88, "body": 36, "caption": 24},
            "spacing": {"padding": 120, "gap": 48},
            "radius": 0,
        },
        theme_markdown="Theme.",
        widgets=[],
        user_prompt="Go",
        widget_chart_ids=None,
        outline=None,
    )
    assert "## Required outline" not in prompt


def test_authoring_rules_ban_ai_tell_decorations() -> None:
    """Editorial refit: no chrome decorations (triangles, stripes, accent rules)."""
    rules = SLIDE_AUTHORING_RULES
    assert "Editorial restraint" in rules
    assert "Diagonal corner triangles" in rules
    assert "Vertical accent stripes" in rules
    assert "Horizontal accent rules" in rules
    assert "Dominance, not equality" in rules


def test_audit_prompt_includes_visual_rendering_checklist() -> None:
    svc = LLMService()
    prompt = svc._build_audit_prompt(
        deck_html='<section class="slide" data-slide-id="s1"></section>',
        tokens={
            "palette": {
                "bg": "#000",
                "text": "#fff",
                "accent": "#f00",
                "muted": "#888",
            },
            "fonts": {"display": "I", "body": "I"},
            "typeScale": {"hero": 200, "title": 88, "body": 36, "caption": 24},
            "spacing": {"padding": 120, "gap": 48},
            "radius": 0,
        },
        theme_markdown="Theme",
    )
    assert "Overlapping elements" in prompt
    assert "decorative line" in prompt.lower()
    assert "Leftover placeholder text" in prompt


def test_audit_prompt_includes_design_checklist() -> None:
    svc = LLMService()
    prompt = svc._build_audit_prompt(
        deck_html='<section class="slide" data-slide-id="s1"></section>',
        tokens={
            "palette": {
                "bg": "#000",
                "text": "#fff",
                "accent": "#f00",
                "muted": "#888",
            },
            "fonts": {"display": "I", "body": "I"},
            "typeScale": {"hero": 200, "title": 88, "body": 36, "caption": 24},
            "spacing": {"padding": 120, "gap": 48},
            "radius": 0,
        },
        theme_markdown="Theme",
    )
    assert "## Slide-deck design checklist" in prompt
    assert "Content shape mismatch" in prompt
    assert "Layout repetition" in prompt
    assert "Moments of impact" in prompt


def test_outline_prompt_includes_reference_doc() -> None:
    svc = LLMService()
    prompt = svc._build_outline_prompt(
        tokens={},
        theme_markdown="T",
        widgets=[],
        user_prompt="focus execs",
        reference_doc="## Finding\nRoot cause: timeout.",
        reference_doc_name="rca.md",
    )
    assert "## Reference document: rca.md" in prompt
    assert "Root cause: timeout." in prompt
    assert "primary content source" in prompt.lower()


def test_outline_prompt_omits_reference_doc_when_none() -> None:
    svc = LLMService()
    prompt = svc._build_outline_prompt(
        tokens={},
        theme_markdown="T",
        widgets=[],
        user_prompt="x",
        reference_doc=None,
        reference_doc_name=None,
    )
    assert "## Reference document:" not in prompt


def test_authoring_rules_include_overflow_guards() -> None:
    assert "≤ 5 words" in SLIDE_AUTHORING_RULES
    assert "padding-right" in SLIDE_AUTHORING_RULES
    assert "1080px" in SLIDE_AUTHORING_RULES


def test_augment_chart_specs_returns_empty_on_invalid_json() -> None:
    class FakeCfg:
        host = "https://test.databricks.com"

        def authenticate(self) -> dict[str, str]:
            return {"Authorization": "Bearer fake-token"}

    class FakeWs:
        config = FakeCfg()

    svc = LLMService(workspace_client=FakeWs())
    with patch.object(svc, "_foundation_model_chat_sync", return_value="not json"):
        out = svc.augment_chart_specs_for_deck(
            widgets_with_data=[{"widget_id": "w1"}],
            slide_outline=[],
            tokens={},
        )
    assert out == []


def test_augment_chart_specs_returns_only_valid_augmentations() -> None:
    class FakeCfg:
        host = "https://test.databricks.com"

        def authenticate(self) -> dict[str, str]:
            return {"Authorization": "Bearer fake-token"}

    class FakeWs:
        config = FakeCfg()

    svc = LLMService(workspace_client=FakeWs())
    payload = {
        "augmentations": [
            {"widget_id": "good"},
            {"highlight": None},
        ]
    }
    with patch.object(
        svc,
        "_foundation_model_chat_sync",
        return_value=json.dumps(payload),
    ):
        out = svc.augment_chart_specs_for_deck(
            widgets_with_data=[{"widget_id": "good"}],
            slide_outline=[{"title": "t", "summary": "s", "layout": "content"}],
            tokens={},
        )
    assert len(out) == 1
    assert out[0].widget_id == "good"


def test_augment_chart_specs_calls_edit_endpoint() -> None:
    class FakeCfg:
        host = "https://test.databricks.com"

        def authenticate(self) -> dict[str, str]:
            return {"Authorization": "Bearer fake-token"}

    class FakeWs:
        config = FakeCfg()

    svc = LLMService(workspace_client=FakeWs())
    with patch.object(
        svc,
        "_foundation_model_chat_sync",
        return_value='{"augmentations":[]}',
    ) as mocked:
        svc.augment_chart_specs_for_deck(
            widgets_with_data=[],
            slide_outline=[],
            tokens={},
        )
    assert mocked.call_args.kwargs.get("endpoint") == svc._edit_endpoint


class _FakeWs:
    class _FakeCfg:
        host = "https://test.databricks.com"

        def authenticate(self) -> dict[str, str]:
            return {"Authorization": "Bearer fake-token"}

    config = _FakeCfg()


def _widgets_with_fields() -> list[dict]:
    return [
        {
            "widget_id": "w1",
            "title": "Top users",
            "available_fields": ["user_email", "event_count"],
            "rows_sample": [
                {"user_email": "a@x.com", "event_count": 42},
                {"user_email": "b@x.com", "event_count": 17},
            ],
        }
    ]


def test_augment_chart_specs_parses_valid_design() -> None:
    svc = LLMService(workspace_client=_FakeWs())
    payload = {
        "augmentations": [
            {
                "widget_id": "w1",
                "highlight": {"field": "user_email", "values": ["a@x.com"]},
                "caption": "Leader",
                "design": {
                    "chart_type": "bar",
                    "category_field": "user_email",
                    "value_field": "event_count",
                    "series_field": None,
                    "aggregate": "none",
                    "sort": "value_desc",
                    "top_n": 10,
                    "orientation": "horizontal",
                },
            }
        ]
    }
    with patch.object(
        svc,
        "_foundation_model_chat_sync",
        return_value=json.dumps(payload),
    ):
        out = svc.augment_chart_specs_for_deck(
            widgets_with_data=_widgets_with_fields(),
            slide_outline=[],
            tokens={},
        )
    assert len(out) == 1
    aug = out[0]
    assert aug.widget_id == "w1"
    assert aug.caption == "Leader"
    assert aug.highlight is not None
    assert aug.design is not None
    assert aug.design.chart_type == "bar"
    assert aug.design.category_field == "user_email"
    assert aug.design.value_field == "event_count"
    assert aug.design.sort == "value_desc"
    assert aug.design.top_n == 10
    assert aug.design.orientation == "horizontal"


def test_augment_chart_specs_nulls_bad_design_preserves_decoration() -> None:
    svc = LLMService(workspace_client=_FakeWs())
    payload = {
        "augmentations": [
            {
                "widget_id": "w1",
                "highlight": {"field": "user_email", "values": ["a@x.com"]},
                "caption": "Keep me",
                "design": {
                    "chart_type": "bar",
                    "category_field": "not_a_real_field",
                    "value_field": "event_count",
                    "aggregate": "none",
                    "sort": "value_desc",
                    "top_n": 8,
                },
            }
        ]
    }
    with patch.object(
        svc,
        "_foundation_model_chat_sync",
        return_value=json.dumps(payload),
    ):
        out = svc.augment_chart_specs_for_deck(
            widgets_with_data=_widgets_with_fields(),
            slide_outline=[],
            tokens={},
        )
    assert len(out) == 1
    aug = out[0]
    assert aug.design is None
    assert aug.caption == "Keep me"
    assert aug.highlight is not None
    assert aug.highlight.field == "user_email"


def test_augment_chart_specs_drops_only_invalid_widget_on_schema_error() -> None:
    svc = LLMService(workspace_client=_FakeWs())
    payload = {
        "augmentations": [
            {
                "highlight": None,
                "design": {"chart_type": "bar"},
            },
            {
                "widget_id": "w1",
                "caption": "valid widget",
                "design": {
                    "chart_type": "line",
                    "category_field": "user_email",
                    "value_field": "event_count",
                },
            },
        ]
    }
    with patch.object(
        svc,
        "_foundation_model_chat_sync",
        return_value=json.dumps(payload),
    ):
        out = svc.augment_chart_specs_for_deck(
            widgets_with_data=_widgets_with_fields(),
            slide_outline=[],
            tokens={},
        )
    assert len(out) == 1
    assert out[0].widget_id == "w1"
    assert out[0].caption == "valid widget"
    assert out[0].design is not None
    assert out[0].design.chart_type == "line"


def test_augment_chart_specs_decoration_only_without_design() -> None:
    svc = LLMService(workspace_client=_FakeWs())
    payload = {
        "augmentations": [
            {
                "widget_id": "w1",
                "highlight": {"field": "user_email", "values": ["a@x.com"]},
                "reference_line": {"axis": "y", "value": 30, "label": "avg"},
                "value_format": "count",
                "caption": "Plain decoration",
            }
        ]
    }
    with patch.object(
        svc,
        "_foundation_model_chat_sync",
        return_value=json.dumps(payload),
    ):
        out = svc.augment_chart_specs_for_deck(
            widgets_with_data=_widgets_with_fields(),
            slide_outline=[],
            tokens={},
        )
    assert len(out) == 1
    aug = out[0]
    assert aug.widget_id == "w1"
    assert aug.design is None
    assert aug.caption == "Plain decoration"
    assert aug.value_format == "count"
    assert aug.reference_line is not None


def test_augment_chart_specs_clamps_top_n() -> None:
    svc = LLMService(workspace_client=_FakeWs())
    payload = {
        "augmentations": [
            {
                "widget_id": "w1",
                "design": {
                    "chart_type": "bar",
                    "category_field": "user_email",
                    "value_field": "event_count",
                    "sort": "value_desc",
                    "top_n": 999,
                },
            }
        ]
    }
    with patch.object(
        svc,
        "_foundation_model_chat_sync",
        return_value=json.dumps(payload),
    ):
        out = svc.augment_chart_specs_for_deck(
            widgets_with_data=_widgets_with_fields(),
            slide_outline=[],
            tokens={},
        )
    assert len(out) == 1
    assert out[0].design is not None
    assert out[0].design.top_n == 20
