from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class TemplateBrand(BaseModel):
    primary: str = "#333333"
    secondary: str = "#666666"
    accent: str = "#0066CC"
    text_dark: str = "#202124"
    text_light: str = "#FFFFFF"
    font: str = "Noto Sans JP"


class TemplateGuidelines(BaseModel):
    total_slides_min: int = 6
    total_slides_max: int = 12
    structure_hint: str = "Overview → Data detail → Insights → Next actions"
    preferred_layouts: list[str] = Field(
        default_factory=lambda: [
            "title",
            "content_basic",
            "content_2col",
            "title_only",
            "closing",
        ]
    )
    style_notes: str = "Concise. One message per slide."
    must_include: list[str] = Field(default_factory=lambda: ["title", "closing"])
    chart_preference: str


class DesignTokens(BaseModel):
    palette: dict[str, str]
    fonts: dict[str, str]
    typeScale: dict[str, int]
    spacing: dict[str, int]
    radius: int = 0


class PptxExtractResult(BaseModel):
    upload_id: str
    suggested_name: str
    theme_markdown: str = ""
    tokens: DesignTokens


class TemplateCreate(BaseModel):
    name: str
    description: str = ""
    google_slides_template_id: str
    theme: str = "light"
    brand: TemplateBrand = Field(default_factory=TemplateBrand)
    guidelines: TemplateGuidelines = Field(
        default_factory=lambda: TemplateGuidelines(chart_preference="auto"),
    )
    tokens: Optional[DesignTokens] = None
    theme_markdown: str = ""
    preset_id: Optional[str] = None
    pptx_file_path: Optional[str] = None
    pptx_upload_id: Optional[str] = None


class Template(TemplateCreate):
    id: str
    thumbnail_url: Optional[str] = None
    created_by: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class Deck(BaseModel):
    id: str
    user_id: str
    template_id: str
    genie_space_id: str
    questions: list[str] = Field(default_factory=list)
    google_slides_template_id: str = ""
    user_prompt: Optional[str] = None
    html_doc: str
    design_tokens: dict[str, Any] = Field(default_factory=dict)
    theme_markdown: str = ""
    status: str = "draft"
    gslides_file_id: str | None = None
    gslides_url: str | None = None
    chart_warnings: list[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DeckRevision(BaseModel):
    id: str
    deck_id: str
    revision_no: int
    html_doc: str
    trigger: str
    comment_note: Optional[str] = None
    created_at: Optional[datetime] = None


class PendingComment(BaseModel):
    id: str
    target_id: str
    note: str
    ts: str


class SaveCommentRequest(BaseModel):
    target_id: str
    note: str


class AddSlideRequest(BaseModel):
    prompt: str


class RegenerateSlideRequest(BaseModel):
    feedback: str | None = None


class DeckMutationResponse(BaseModel):
    deck: Deck
    revision_no: int


class WidgetInfo(BaseModel):
    widget_id: str
    title: str
    viz_type: str
    columns: list[str] = Field(default_factory=list)
    row_count: int = 0
    query_result_summary: Optional[str] = None
    capture_status: str = "pending"
    sql_text: Optional[str] = None
    lakeview_spec: Optional[dict[str, Any]] = None


class OutlineSlide(BaseModel):
    """One slide in the proposed outline."""

    layout: str  # one of the 24 known layouts
    title: str
    summary: str  # 1-line description of slide content
    notes: str = ""  # optional speaker notes / extra detail


class OutlineRequest(BaseModel):
    template_id: str
    genie_space_id: str
    questions: list[str] = Field(default_factory=list)
    user_prompt: str | None = None
    reference_doc: str | None = None  # plain text or markdown body
    reference_doc_name: str | None = None  # optional filename for the LLM


class OutlineResponse(BaseModel):
    slides: list[OutlineSlide]


class AuditIssue(BaseModel):
    slide_id: str
    severity: str  # P0 | P1 | P2
    message: str
    fix_hint: str


class AuditResponse(BaseModel):
    deck: Deck
    issues: list[AuditIssue]


class GenerationRequest(BaseModel):
    template_id: str
    genie_space_id: str
    questions: list[str] = Field(default_factory=list)
    user_prompt: Optional[str] = None
    format: str | None = None  # "html" | "pptx"; None treated as html
    outline: list[OutlineSlide] | None = (
        None  # when provided, deck follows this outline
    )
    high_quality: bool = True


class GenerationResult(BaseModel):
    slides_url: str
    slide_count: int
    warnings: list[str] = Field(default_factory=list)
    skipped_widgets: list[str] = Field(default_factory=list)
    format: str = "html"


class ChartHighlight(BaseModel):
    field: str  # column / encoding dimension to highlight
    values: list[str]


class ChartReferenceLine(BaseModel):
    axis: str  # "y" or "x"
    value: float | int
    label: str


class ChartAugmentation(BaseModel):
    """Per-widget chart augmentation from LLM. Omitted / empty fields mean plain."""

    widget_id: str
    highlight: ChartHighlight | None = None
    y_range: tuple[float, float] | None = None
    reference_line: ChartReferenceLine | None = None
    value_format: str | None = None  # currency | percent | count | duration
    caption: str | None = None
