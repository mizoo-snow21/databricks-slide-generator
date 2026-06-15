from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from models import (
    DesignTokens,
    PptxExtractResult,
    Template,
    TemplateCreate,
)
from services.template_presets import PRESETS, get_preset
from services.template_service import TemplateService
from services.pptx_template_storage import (
    cleanup_old_temp_files,
    finalize_pptx_for_template,
    save_pptx_temp,
)
from services.pptx_theme_extractor import extract_design_tokens_from_pptx

_STATE_DIR = os.environ.get("GENIE_SLIDE_STATE_DIR", "./data")
templates_service = TemplateService(
    use_memory=True,
    persist_path=os.path.join(_STATE_DIR, "templates.json"),
)

router = APIRouter(prefix="/api/templates", tags=["templates"])


class PresetSummary(BaseModel):
    id: str
    name: str
    description: str
    tokens: DesignTokens
    theme_markdown: str


class GoogleSlidesImportRequest(BaseModel):
    url: str


class GoogleSlidesImportResult(BaseModel):
    google_slides_template_id: str
    suggested_name: str
    tokens: DesignTokens
    theme_markdown: str


@router.get("", response_model=list[Template])
def list_templates() -> list[Template]:
    return templates_service.list_all()


@router.get("/presets", response_model=list[PresetSummary])
def list_presets() -> list[PresetSummary]:
    return [
        PresetSummary(
            id=p["id"],
            name=p["name"],
            description=p["description"],
            tokens=DesignTokens(**p["tokens"]),
            theme_markdown=p.get("theme_markdown", ""),
        )
        for p in PRESETS
    ]


@router.post(
    "/from-preset/{preset_id}",
    response_model=Template,
    status_code=status.HTTP_201_CREATED,
)
def create_from_preset(preset_id: str) -> Template:
    p = get_preset(preset_id)
    if p is None:
        raise HTTPException(status_code=404, detail=f"Preset {preset_id!r} not found")
    payload = TemplateCreate(
        name=p["name"],
        description=p["description"],
        google_slides_template_id="",
        theme="light"
        if p["tokens"]["palette"]["bg"].lower() in ("#ffffff", "#fafafa", "#fff")
        else "dark",
        tokens=DesignTokens(**p["tokens"]),
        theme_markdown=p.get("theme_markdown", ""),
        preset_id=preset_id,
    )
    return templates_service.create(payload, user_id="")


def _suggested_name_from_pptx_filename(filename: str) -> str:
    stem = Path(filename).stem
    return stem.replace("_", " ").replace("-", " ").strip().title() or "Uploaded deck"


@router.post("/extract-pptx", response_model=PptxExtractResult)
def extract_pptx_theme(file: UploadFile = File(...)) -> PptxExtractResult:
    cleanup_old_temp_files()
    if not file.filename or not file.filename.lower().endswith(".pptx"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="File must be a .pptx",
        )
    pptx_bytes = file.file.read()
    if not pptx_bytes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Empty file")
    try:
        tokens_dict = extract_design_tokens_from_pptx(pptx_bytes)
    except Exception as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read PPTX theme: {e}",
        ) from e

    upload_id = str(uuid.uuid4())
    save_pptx_temp(upload_id, pptx_bytes)
    return PptxExtractResult(
        upload_id=upload_id,
        suggested_name=_suggested_name_from_pptx_filename(file.filename),
        theme_markdown="",
        tokens=DesignTokens(**tokens_dict),
    )


@router.post("/import-from-google-slides", response_model=GoogleSlidesImportResult)
def import_from_google_slides(
    body: GoogleSlidesImportRequest,
) -> GoogleSlidesImportResult:
    """Read a Google Slides presentation and extract palette, fonts, and a name.

    Requires gcloud auth on the runtime (the vendored gslides_builder uses
    gcloud-printed access tokens). Returns a payload the frontend can pre-fill
    the admin form with — the user still confirms before saving.
    """
    pres_id = _extract_presentation_id(body.url)
    if not pres_id:
        raise HTTPException(
            status_code=400, detail="Could not extract presentation ID from URL"
        )
    try:
        from vendor.gslides_builder import get_presentation  # type: ignore
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Google Slides integration unavailable: {e}",
        ) from e
    try:
        pres = get_presentation(pres_id)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch presentation (gcloud auth required): {e}",
        ) from e

    tokens = _extract_tokens_from_presentation(pres)
    name = pres.get("title") or "Imported deck"
    theme_md = (
        f"Imported from Google Slides ({name}). "
        f"Auto-extracted brand colors and fonts from the presentation theme."
    )
    return GoogleSlidesImportResult(
        google_slides_template_id=pres_id,
        suggested_name=name,
        tokens=tokens,
        theme_markdown=theme_md,
    )


@router.get("/{template_id}", response_model=Template)
def get_template(template_id: str) -> Template:
    template = templates_service.get(template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return template


@router.post("", response_model=Template, status_code=status.HTTP_201_CREATED)
def create_template(data: TemplateCreate) -> Template:
    pptx_uid = data.pptx_upload_id
    template = templates_service.create(data, user_id="")
    if pptx_uid:
        path = finalize_pptx_for_template(pptx_uid, template.id)
        if path:
            updated = templates_service.update(template.id, {"pptx_file_path": path})
            if updated is not None:
                return updated
    return template


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(template_id: str) -> None:
    if not templates_service.delete(template_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


# === Helpers ===


def _extract_presentation_id(url: str) -> str | None:
    """Pull the presentation ID from any Google Slides URL or raw ID."""
    s = url.strip()
    if not s:
        return None
    # Already an ID (no slashes, looks alphanumeric)
    if "/" not in s and len(s) >= 16 and re.match(r"^[A-Za-z0-9_-]+$", s):
        return s
    m = re.search(r"/presentation/d/([A-Za-z0-9_-]+)", s)
    if m:
        return m.group(1)
    return None


def _hex(rgb_color: dict[str, Any] | None) -> str | None:
    if not rgb_color:
        return None
    rgb = rgb_color.get("rgbColor") or rgb_color
    if not isinstance(rgb, dict):
        return None
    r = int(round(rgb.get("red", 0) * 255))
    g = int(round(rgb.get("green", 0) * 255))
    b = int(round(rgb.get("blue", 0) * 255))
    return f"#{r:02x}{g:02x}{b:02x}"


def _extract_tokens_from_presentation(pres: dict[str, Any]) -> DesignTokens:
    """Best-effort extraction of palette + fonts from a Google Slides presentation."""
    masters = pres.get("masters") or []
    color_scheme = (
        masters[0].get("pageProperties", {}).get("colorScheme", {}).get("colors", [])
        if masters
        else []
    )
    by_type: dict[str, str] = {}
    for c in color_scheme:
        t = c.get("type")
        h = _hex({"rgbColor": c.get("color", {}).get("rgbColor", {})})
        if t and h:
            by_type[t] = h

    bg = by_type.get("LIGHT1") or by_type.get("BACKGROUND1") or "#ffffff"
    text = by_type.get("DARK1") or by_type.get("TEXT1") or "#1b3139"
    accent = by_type.get("ACCENT1") or by_type.get("ACCENT2") or "#ff3621"
    muted = by_type.get("DARK2") or by_type.get("LIGHT2") or "#6f7989"

    # Try to find a font name from a TITLE placeholder on the master.
    font = "DM Sans"
    for master in masters:
        for el in master.get("pageElements", []) or []:
            shape = el.get("shape")
            if not shape:
                continue
            text_el = shape.get("text")
            if not text_el:
                continue
            for child in text_el.get("textElements", []) or []:
                run = child.get("textRun") or {}
                style = run.get("style") or {}
                fam = style.get("fontFamily")
                if fam:
                    font = fam
                    break
            if font != "DM Sans":
                break
        if font != "DM Sans":
            break

    is_dark = _is_dark(bg)
    return DesignTokens(
        palette={"bg": bg, "text": text, "accent": accent, "muted": muted},
        fonts={"display": f"'{font}', sans-serif", "body": f"'{font}', sans-serif"},
        typeScale={"hero": 180, "title": 80, "body": 32, "caption": 22},
        spacing={"padding": 120, "gap": 48},
        radius=4 if not is_dark else 0,
    )


def _is_dark(hex_color: str) -> bool:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return False
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return luminance < 0.5
