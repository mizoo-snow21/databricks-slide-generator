from __future__ import annotations

from datetime import datetime
from typing import Optional

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


class TemplateCreate(BaseModel):
    name: str
    description: str = ""
    google_slides_template_id: str
    theme: str = "light"
    brand: TemplateBrand = Field(default_factory=TemplateBrand)
    guidelines: TemplateGuidelines = Field(
        default_factory=lambda: TemplateGuidelines(chart_preference="auto"),
    )


class Template(TemplateCreate):
    id: str
    thumbnail_url: Optional[str] = None
    created_by: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DashboardInfo(BaseModel):
    dashboard_id: str
    name: str
    description: str = ""
    widget_count: int = 0
    updated_at: Optional[str] = None


class WidgetInfo(BaseModel):
    widget_id: str
    title: str
    viz_type: str
    columns: list[str] = Field(default_factory=list)
    row_count: int = 0
    query_result_summary: Optional[str] = None
    capture_status: str = "pending"


class GenerationRequest(BaseModel):
    template_id: str
    dashboard_id: str
    user_prompt: Optional[str] = None


class GenerationResult(BaseModel):
    google_slides_url: str
    slide_count: int
    warnings: list[str] = Field(default_factory=list)
    skipped_widgets: list[str] = Field(default_factory=list)


class GenerationHistoryRecord(BaseModel):
    id: str
    template_id: str
    dashboard_id: str
    user_id: str
    user_prompt: Optional[str] = None
    google_slides_url: str
    slide_count: int
    created_at: datetime
