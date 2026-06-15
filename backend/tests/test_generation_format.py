"""Tests for generation output format (HTML vs PPTX) on request/result models."""

from __future__ import annotations

from models import GenerationRequest, GenerationResult


def test_generation_request_default_format() -> None:
    req = GenerationRequest(template_id="t1", genie_space_id="d1")
    assert req.format is None


def test_generation_result_includes_format() -> None:
    assert "format" in GenerationResult.model_fields
    res = GenerationResult(slides_url="/api/slides/x", slide_count=1)
    assert res.format == "html"
    res_pptx = GenerationResult(
        slides_url="/api/slides/y",
        slide_count=2,
        format="pptx",
    )
    assert res_pptx.format == "pptx"
