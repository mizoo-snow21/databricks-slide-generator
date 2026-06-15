from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import zipfile
import time as _time
import urllib.request
from io import BytesIO
from pathlib import Path
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse, Response

from auth.user_workspace import build_default_workspace_client, get_user_workspace_client
from models import (
    AddSlideRequest,
    AuditIssue,
    AuditResponse,
    ChartAugmentation,
    Deck,
    DeckMutationResponse,
    RegenerateSlideRequest,
    GenerationRequest,
    OutlineRequest,
    OutlineResponse,
    OutlineSlide,
    PendingComment,
    SaveCommentRequest,
    Template,
    WidgetInfo,
)
from routers.templates import templates_service
from services.brand_styles import CATEGORY_PALETTE_BY_PRESET
from services.deck_service import DeckMemoryRepo, DeckService, DeckValidationError
from services import genie_service
from services.genie_service import summarize_widget_rows
from services.inspector_script import inject_inspector
from services.llm_service import LLMService
from services.pptx_slides_service import generate_pptx_slides

_deck_llm = LLMService(workspace_client=build_default_workspace_client())

_STATE_DIR = os.environ.get("GENIE_SLIDE_STATE_DIR", "./data")
deck_repo = DeckMemoryRepo(persist_path=os.path.join(_STATE_DIR, "decks.json"))
deck_service = DeckService(llm=_deck_llm, repo=deck_repo)

_PPTX_TEMPLATE_CACHE_DIR = Path("/tmp/genie-slide-pptx-templates")
_PPTX_TEMPLATE_URLS = {
    # Maps preset id (and the corresponding template name) to a downloadable URL.
    # Source: https://github.com/TSHuss/Databricks-slide-skill (raw file).
    "databricks-corp": (
        "https://raw.githubusercontent.com/TSHuss/Databricks-slide-skill/"
        "main/assets/databricks/template.pptx"
    ),
    "databricks-corp-dark": (
        "https://raw.githubusercontent.com/TSHuss/Databricks-slide-skill/"
        "main/assets/databricks/template.pptx"
    ),
}


_EXPERIMENTAL_HTML_EXPORT_NOTE = "Experimental: PPTX/Google Slides export uses LLM HTML→slide conversion; verify output."


def _ensure_pptx_template(preset_id: str) -> Path | None:
    """Return a local Path to the cached PPTX template, downloading on first use.

    File is too large (~22MB) to bundle in the Databricks Apps deploy
    (10MB per-file source-import cap), so we lazy-fetch on demand and
    cache to /tmp. Returns None if the preset has no mapped URL or all
    download retries fail.
    """
    url = _PPTX_TEMPLATE_URLS.get(preset_id)
    if not url:
        return None
    _PPTX_TEMPLATE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = _PPTX_TEMPLATE_CACHE_DIR / f"{preset_id}.pptx"
    if cache_path.is_file() and cache_path.stat().st_size > 1_000_000:
        return cache_path
    last_err: Exception | None = None
    for attempt, delay in enumerate((1, 2, 4)):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
                data = response.read()
            cache_path.write_bytes(data)
            return cache_path
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < 2:
                _time.sleep(delay)
    print(
        f"[pptx-template] failed to download {preset_id} after 3 attempts: {last_err}",
        file=sys.stderr,
    )
    return None


def warm_pptx_template_cache() -> None:
    """Best-effort download of all mapped PPTX templates at startup."""
    for preset_id in _PPTX_TEMPLATE_URLS:
        try:
            _ensure_pptx_template(preset_id)
        except Exception:
            pass


def _template_name_matches_preset(name_lower: str, preset_id: str) -> bool:
    if preset_id in name_lower:
        return True
    phrase = preset_id.replace("-", " ")
    if phrase in name_lower:
        return True
    parts = [p for p in preset_id.split("-") if p]
    return bool(parts) and all(part in name_lower for part in parts)


def _resolve_preset_id_from_template_name(template_name: str) -> str | None:
    """Match preset ids from template display name (longer / more specific ids first)."""
    name_lower = template_name.lower()
    for preset_id in (
        "databricks-corp-dark",
        "databricks-corp",
        "databricks-brand",
        "editorial-noir",
        "minimal-light",
        "tech-graphite",
    ):
        if _template_name_matches_preset(name_lower, preset_id):
            return preset_id
    return None


def _resolve_pptx_template_for_deck(deck: Deck) -> Path | None:
    """Resolve the PPTX template path by matching the deck's template name.

    The deck doesn't store the preset id directly. We match on template
    name to keep this loose — if the template was created from the
    databricks-corp / databricks-corp-dark preset, its name matches those
    presets (dark checked before light so "Corporate Dark" does not pick
    the light preset).
    """
    template = templates_service.get(deck.template_id)
    if template is None:
        return None
    if template.pptx_file_path:
        p = Path(template.pptx_file_path)
        if p.is_file():
            return p
    preset_id = template.preset_id or _resolve_preset_id_from_template_name(
        template.name
    )
    if preset_id:
        return _ensure_pptx_template(preset_id)
    return None


def get_deck_service() -> DeckService:
    return deck_service


def get_llm_service() -> LLMService:
    return _deck_llm


def get_user_id(
    x_forwarded_email: Annotated[str | None, Header(alias="X-Forwarded-Email")] = None,
) -> str:
    if x_forwarded_email and x_forwarded_email.strip():
        return x_forwarded_email.strip()
    return "demo-user"


router = APIRouter(prefix="/api/decks", tags=["decks"])


def _http_from_validation(exc: DeckValidationError) -> HTTPException:
    msg = str(exc)
    low = msg.lower()
    if "not found" in low:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


def _tokens_dict_from_template(t: Template) -> dict[str, Any]:
    if t.tokens is not None:
        return t.tokens.model_dump()
    # No explicit tokens (manual Admin template): derive a coherent palette
    # from the template's visible controls so Primary color / Theme / Font
    # actually drive the deck. theme flips bg/text; accent = brand.primary.
    theme = (t.theme or "light").lower()
    if theme == "dark":
        bg = t.brand.text_dark
        text = t.brand.text_light
    else:
        bg = t.brand.text_light
        text = t.brand.text_dark
    return {
        "palette": {
            "bg": bg,
            "text": text,
            "accent": t.brand.primary,
            "muted": t.brand.secondary,
        },
        "fonts": {"display": t.brand.font, "body": t.brand.font},
        "typeScale": {"hero": 200, "title": 88, "body": 36, "caption": 24},
        "spacing": {"padding": 120, "gap": 48},
        "radius": 0,
    }


def _widgets_from_genie(
    client: Any,
    genie_space_id: str,
    questions: list[str],
) -> tuple[list[WidgetInfo], dict[str, list[dict[str, Any]]], list[str]]:
    """Run Genie questions and build WidgetInfo + row data for chart prerender."""
    ok_answers, warnings = asyncio.run(
        genie_service.ask_many(client, genie_space_id, questions)
    )
    if not ok_answers:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="All questions failed: " + "; ".join(warnings),
        )
    widgets: list[WidgetInfo] = []
    rows_by_widget: dict[str, list[dict[str, Any]]] = {}
    for i, answer in enumerate(ok_answers):
        widget_id = f"q{i}"
        widgets.append(
            WidgetInfo(
                widget_id=widget_id,
                title=answer.question,
                viz_type="auto",
                columns=answer.columns,
                row_count=len(answer.rows),
                sql_text=answer.sql,
                query_result_summary=summarize_widget_rows(answer.rows),
            )
        )
        rows_by_widget[widget_id] = answer.rows
    return widgets, rows_by_widget, warnings


_DARK_TONE_PRESETS = frozenset(
    {"databricks-corp-dark", "editorial-noir", "tech-graphite"}
)


def _bg_tone_for_preset(preset_id: str | None) -> str:
    """Map a preset id to 'dark' or 'light' for chart text-color adaptation."""
    return "dark" if preset_id in _DARK_TONE_PRESETS else "light"


def _prerender_widget_chart_data_uris(
    widgets: list[WidgetInfo],
    rows_by_widget: dict[str, list[dict[str, Any]]],
    bg_tone: str = "light",
    palette: list[str] | None = None,
    outline: list[dict] | None = None,
    tokens: dict[str, Any] | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """Fetch widget data, convert to vega-lite, render as PNG data URIs.

    `bg_tone` adapts chart axis/legend/title text colors to be visible
    against the slide background.

    `palette` overrides the default Vega-Lite categorical range when set
    (e.g. brand-aligned colors for the deck preset).
    """
    import sys

    def _log(msg: str) -> None:
        print(f"[charts] {msg}", file=sys.stderr, flush=True)

    errors: dict[str, str] = {}
    if not widgets:
        _log("no widgets — skipping prerender")
        return {}, {}

    from base64 import b64encode

    from services.pptx_slides_service import _render_chart_to_png
    from services.vegalite_service import (
        _filter_nulls_for_chart,
        apply_augmentation_to_spec,
        convert_widget_to_vegalite,
        widget_spec_from_columns,
    )

    tok = tokens or {}
    widgets_with_data: list[dict[str, Any]] = []
    for w in widgets:
        rlist = rows_by_widget.get(w.widget_id) or []
        if not rlist:
            continue
        spec = widget_spec_from_columns(w.title, w.columns, rlist)
        widgets_with_data.append(
            {
                "widget_id": w.widget_id,
                "title": w.title,
                "encodings": spec.get("encodings", {}),
                "chart_type": spec.get("widgetType"),
                "available_fields": list(rlist[0].keys()) if rlist else [],
                "rows_sample": rlist[:10],
                "row_count": len(rlist),
                "aggregates": summarize_widget_rows(rlist),
            }
        )

    augmentations_by_wid: dict[str, ChartAugmentation] = {}
    if widgets_with_data:
        try:
            aug_list = _deck_llm.augment_chart_specs_for_deck(
                widgets_with_data=widgets_with_data,
                slide_outline=list(outline or []),
                tokens=tok,
            )
            augmentations_by_wid = {a.widget_id: a for a in aug_list}
        except Exception as exc:
            print(
                f"[chart-augment] failed top-level: {exc}",
                file=sys.stderr,
                flush=True,
            )

    out: dict[str, str] = {}
    for w in widgets:
        rows = rows_by_widget.get(w.widget_id) or []
        if rows:
            w.query_result_summary = summarize_widget_rows(rows)
            w.row_count = len(rows)
        if not rows:
            if w.widget_id not in errors:
                errors[w.widget_id] = "no data rows for chart"
            _log(f"widget {w.widget_id} ({w.title}): no data rows")
            continue
        spec = widget_spec_from_columns(w.title, w.columns, rows)
        try:
            cleaned_rows, n_dropped = _filter_nulls_for_chart(spec, rows)
            if n_dropped > 0:
                errors[w.widget_id] = (
                    f"chart skipped {n_dropped} row(s) with NULL in axis/color fields"
                )
            vl = convert_widget_to_vegalite(
                spec,
                cleaned_rows,
                bg_tone=bg_tone,
                palette=palette,
            )
            if not vl:
                errors[w.widget_id] = "vega-lite conversion returned empty"
                _log(f"widget {w.widget_id} ({w.title}): vega conversion None")
                continue
            aug = augmentations_by_wid.get(w.widget_id)
            if aug is not None:
                vl = apply_augmentation_to_spec(
                    vl,
                    cleaned_rows,
                    aug,
                    tone=bg_tone,
                    palette=palette,
                    tokens=tok,
                )
            png = _render_chart_to_png(vl)
            out[w.widget_id] = "data:image/png;base64," + b64encode(png).decode("ascii")
            _log(f"widget {w.widget_id} ({w.title}): rendered {len(png)} bytes")
        except Exception as e:
            errors[w.widget_id] = f"render: {e}"
            _log(f"widget {w.widget_id} ({w.title}): render FAILED: {e}")
            continue
    _log(f"prerendered {len(out)}/{len(widgets)} widget charts")
    return out, errors


@router.get("", response_model=list[Deck])
def list_decks(
    user_id: Annotated[str, Depends(get_user_id)],
    svc: Annotated[DeckService, Depends(get_deck_service)],
) -> list[Deck]:
    return svc.list_decks(user_id)


@router.post(
    "/import-pptx",
    response_model=Deck,
    status_code=status.HTTP_201_CREATED,
)
async def import_pptx(
    user_id: Annotated[str, Depends(get_user_id)],
    svc: Annotated[DeckService, Depends(get_deck_service)],
    file: UploadFile = File(...),
    template_id: str = Form(...),
) -> Deck:
    template = templates_service.get(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    if not file.filename or not file.filename.lower().endswith(".pptx"):
        raise HTTPException(status_code=400, detail="Expected a .pptx file")
    contents = await file.read()
    if len(contents) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 50MB)")
    try:
        return svc.import_deck_from_pptx(
            user_id=user_id,
            template_id=template_id,
            pptx_bytes=contents,
            preset_id=template.preset_id
            or _resolve_preset_id_from_template_name(template.name),
            design_tokens=_tokens_dict_from_template(template),
            theme_markdown=template.theme_markdown or "",
            google_slides_template_id=template.google_slides_template_id or "",
        )
    except DeckValidationError as e:
        raise _http_from_validation(e) from e
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to import PPTX: {e}"
        ) from e


@router.post("/outline", response_model=OutlineResponse)
def post_deck_outline(
    body: OutlineRequest,
    _user_id: Annotated[str, Depends(get_user_id)],
    svc: Annotated[DeckService, Depends(get_deck_service)],
    client: Annotated[Any, Depends(get_user_workspace_client)],
) -> OutlineResponse:
    template = templates_service.get(body.template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    tokens = _tokens_dict_from_template(template)
    theme_markdown = template.theme_markdown or ""
    widgets, rows_by_widget, genie_warnings = _widgets_from_genie(
        client, body.genie_space_id, body.questions
    )
    for errmsg in genie_warnings:
        print(
            f"[outline] genie question failed: {errmsg}",
            file=sys.stderr,
            flush=True,
        )
    for w in widgets:
        rows = rows_by_widget.get(w.widget_id, [])
        summary = summarize_widget_rows(rows)
        if summary:
            w.query_result_summary = summary
            w.row_count = len(rows)
    try:
        slides = svc.generate_outline(
            tokens=tokens,
            theme_markdown=theme_markdown,
            widgets=widgets,
            user_prompt=body.user_prompt,
            reference_doc=body.reference_doc,
            reference_doc_name=body.reference_doc_name,
        )
    except DeckValidationError as e:
        raise _http_from_validation(e) from e
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from e
    return OutlineResponse(slides=[OutlineSlide(**s) for s in slides])


_ALLOWED_REF_DOC_SUFFIXES = (".txt", ".md", ".markdown")


@router.post("/outline/upload-doc")
async def upload_outline_reference_doc(
    file: UploadFile = File(...),
) -> dict[str, str]:
    """Accept a small text/markdown file; return body + filename for outline requests."""
    name = (file.filename or "").strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing filename",
        )
    lower = name.lower()
    if not lower.endswith(_ALLOWED_REF_DOC_SUFFIXES):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .txt, .md, and .markdown files are allowed",
        )
    raw = await file.read()
    if len(raw) > 2 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large (max 2MB)",
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    return {"reference_doc": text, "reference_doc_name": name}


@router.post("/{deck_id}/audit", response_model=AuditResponse)
def audit_deck(
    deck_id: str,
    user_id: Annotated[str, Depends(get_user_id)],
    svc: Annotated[DeckService, Depends(get_deck_service)],
) -> AuditResponse:
    """Run audit-and-fix on an existing deck (used by Edit page action)."""
    try:
        deck, issues = svc.audit_and_fix_deck(deck_id=deck_id, user_id=user_id)
    except DeckValidationError as e:
        raise _http_from_validation(e) from e
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from e
    return AuditResponse(deck=deck, issues=[AuditIssue(**i) for i in issues])


@router.get("/{deck_id}", response_model=Deck)
def get_deck(
    deck_id: str,
    user_id: Annotated[str, Depends(get_user_id)],
    svc: Annotated[DeckService, Depends(get_deck_service)],
) -> Deck:
    deck = svc.get_deck(deck_id, user_id)
    if deck is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return deck


@router.post("", response_model=Deck, status_code=status.HTTP_201_CREATED)
def create_deck(
    body: GenerationRequest,
    user_id: Annotated[str, Depends(get_user_id)],
    svc: Annotated[DeckService, Depends(get_deck_service)],
    client: Annotated[Any, Depends(get_user_workspace_client)],
) -> Deck:
    template = templates_service.get(body.template_id)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Template not found"
        )
    tokens = _tokens_dict_from_template(template)
    theme_markdown = template.theme_markdown or ""
    widgets, rows_by_widget, genie_warnings = _widgets_from_genie(
        client, body.genie_space_id, body.questions
    )
    resolved_preset_id = template.preset_id or _resolve_preset_id_from_template_name(
        template.name
    )
    brand_palette = CATEGORY_PALETTE_BY_PRESET.get(resolved_preset_id)
    outline_dicts: list[dict] | None = None
    if body.outline:
        outline_dicts = [s.model_dump() for s in body.outline]
    widget_charts, chart_errors = _prerender_widget_chart_data_uris(
        widgets,
        rows_by_widget,
        bg_tone=_bg_tone_for_preset(resolved_preset_id),
        palette=brand_palette,
        outline=outline_dicts,
        tokens=tokens,
    )
    chart_warnings = [f"{wid}: {msg}" for wid, msg in sorted(chart_errors.items())]
    chart_warnings.extend(genie_warnings)
    try:
        deck = svc.generate_deck(
            user_id=user_id,
            template_id=body.template_id,
            genie_space_id=body.genie_space_id,
            questions=body.questions,
            google_slides_template_id=template.google_slides_template_id,
            user_prompt=body.user_prompt,
            tokens=tokens,
            theme_markdown=theme_markdown,
            widgets=widgets,
            widget_charts=widget_charts,
            chart_warnings=chart_warnings,
            preset_id=resolved_preset_id,
            outline=outline_dicts,
        )
        if body.high_quality:
            try:
                deck, _ = svc.audit_and_fix_deck(deck_id=deck.id, user_id=user_id)
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"High-quality audit failed: {exc}",
                ) from exc
        return deck
    except DeckValidationError as e:
        raise _http_from_validation(e) from e
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from e


@router.get("/{deck_id}/comments", response_model=list[PendingComment])
def list_comments(
    deck_id: str,
    user_id: Annotated[str, Depends(get_user_id)],
    svc: Annotated[DeckService, Depends(get_deck_service)],
) -> list[PendingComment]:
    try:
        return svc.list_pending_comments(deck_id=deck_id, user_id=user_id)
    except DeckValidationError as e:
        raise _http_from_validation(e) from e


@router.post("/{deck_id}/comments", response_model=DeckMutationResponse)
def save_comment(
    deck_id: str,
    body: SaveCommentRequest,
    user_id: Annotated[str, Depends(get_user_id)],
    svc: Annotated[DeckService, Depends(get_deck_service)],
) -> DeckMutationResponse:
    try:
        deck, revision_no = svc.save_comment(
            deck_id=deck_id,
            user_id=user_id,
            target_id=body.target_id,
            note=body.note,
        )
        return DeckMutationResponse(deck=deck, revision_no=revision_no)
    except DeckValidationError as e:
        raise _http_from_validation(e) from e


@router.post(
    "/{deck_id}/comments/{comment_id}/apply",
    response_model=DeckMutationResponse,
)
def apply_comment(
    deck_id: str,
    comment_id: str,
    user_id: Annotated[str, Depends(get_user_id)],
    svc: Annotated[DeckService, Depends(get_deck_service)],
) -> DeckMutationResponse:
    try:
        deck, revision_no = svc.apply_comment(
            deck_id=deck_id, user_id=user_id, comment_id=comment_id
        )
        return DeckMutationResponse(deck=deck, revision_no=revision_no)
    except DeckValidationError as e:
        raise _http_from_validation(e) from e
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from e


@router.delete("/{deck_id}/comments/{comment_id}", response_model=DeckMutationResponse)
def discard_comment(
    deck_id: str,
    comment_id: str,
    user_id: Annotated[str, Depends(get_user_id)],
    svc: Annotated[DeckService, Depends(get_deck_service)],
) -> DeckMutationResponse:
    try:
        deck, revision_no = svc.discard_comment(
            deck_id=deck_id, user_id=user_id, comment_id=comment_id
        )
        return DeckMutationResponse(deck=deck, revision_no=revision_no)
    except DeckValidationError as e:
        raise _http_from_validation(e) from e


@router.post("/{deck_id}/slides", response_model=DeckMutationResponse)
def add_slide(
    deck_id: str,
    body: AddSlideRequest,
    user_id: Annotated[str, Depends(get_user_id)],
    svc: Annotated[DeckService, Depends(get_deck_service)],
) -> DeckMutationResponse:
    try:
        deck, revision_no = svc.add_slide(
            deck_id=deck_id, user_id=user_id, prompt=body.prompt
        )
        return DeckMutationResponse(deck=deck, revision_no=revision_no)
    except DeckValidationError as e:
        raise _http_from_validation(e) from e
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from e


@router.delete("/{deck_id}/slides/{slide_id}", response_model=DeckMutationResponse)
def delete_slide(
    deck_id: str,
    slide_id: str,
    user_id: Annotated[str, Depends(get_user_id)],
    svc: Annotated[DeckService, Depends(get_deck_service)],
) -> DeckMutationResponse:
    try:
        deck, revision_no = svc.delete_slide(
            deck_id=deck_id, user_id=user_id, slide_id=slide_id
        )
        return DeckMutationResponse(deck=deck, revision_no=revision_no)
    except DeckValidationError as e:
        raise _http_from_validation(e) from e


@router.post(
    "/{deck_id}/slides/{slide_id}/regenerate",
    response_model=DeckMutationResponse,
)
def regenerate_slide(
    deck_id: str,
    slide_id: str,
    body: RegenerateSlideRequest,
    user_id: Annotated[str, Depends(get_user_id)],
    svc: Annotated[DeckService, Depends(get_deck_service)],
) -> DeckMutationResponse:
    try:
        deck, revision_no = svc.regenerate_slide(
            deck_id=deck_id,
            user_id=user_id,
            slide_id=slide_id,
            feedback=(body.feedback or "").strip(),
        )
    except DeckValidationError as e:
        raise _http_from_validation(e) from e
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from e
    return DeckMutationResponse(deck=deck, revision_no=revision_no)


@router.get("/{deck_id}/edit-html")
def edit_html(
    deck_id: str,
    user_id: Annotated[str, Depends(get_user_id)],
    svc: Annotated[DeckService, Depends(get_deck_service)],
) -> HTMLResponse:
    deck = svc.get_deck(deck_id, user_id)
    if deck is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    html_with_inspector = inject_inspector(deck.html_doc)
    return HTMLResponse(content=html_with_inspector)


def _html_to_spec_slides(deck_html: str, llm: LLMService) -> list[dict]:
    """Convert deck HTML to create-from-spec JSON via LLM."""
    raw = llm.html_to_spec_json(deck_html=deck_html)
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    parsed = json.loads(text)
    if not isinstance(parsed, list):
        raise ValueError("LLM html_to_spec returned non-array JSON")
    return parsed


def _brand_from_tokens(deck) -> dict:
    """Map design_tokens.palette/fonts to legacy brand dict."""
    palette = (
        (deck.design_tokens or {}).get("palette", {})
        if isinstance(deck.design_tokens, dict)
        else {}
    )
    fonts = (
        (deck.design_tokens or {}).get("fonts", {})
        if isinstance(deck.design_tokens, dict)
        else {}
    )
    return {
        "primary": palette.get("accent", "#0066CC"),
        "secondary": palette.get("muted", "#666666"),
        "accent": palette.get("accent", "#0066CC"),
        "text_dark": palette.get("text", "#202124"),
        "text_light": palette.get("bg", "#FFFFFF"),
        "font": fonts.get("display", "Noto Sans JP"),
    }


_LEAK_TEXT_RE = re.compile(
    r"\b(?:lorem ipsum|xxxx|click to add|tap to enter|replace (?:with|me)|"
    r"this (?:is a )?(?:layout|slide|page) layout|sample text|insert (?:title|text))\b",
    re.IGNORECASE,
)
_AT_RE = re.compile(r"<a:t[^>]*>([^<]*)</a:t>")


def _check_placeholder_leak(pptx_bytes: bytes) -> list[str]:
    """Scan exported PPTX <a:t> text runs for unfilled placeholder strings."""
    leaks: list[str] = []
    try:
        with zipfile.ZipFile(BytesIO(pptx_bytes)) as zf:
            for name in zf.namelist():
                if not name.startswith("ppt/slides/slide") or not name.endswith(".xml"):
                    continue
                content = zf.read(name).decode("utf-8", errors="ignore")
                for run_text in _AT_RE.findall(content):
                    for m in _LEAK_TEXT_RE.finditer(run_text):
                        leaks.append(f"{name}: {m.group(0)!r}")
                        if len(leaks) >= 10:
                            return leaks
    except Exception as exc:
        print(f"[pptx-leak-check] scan failed: {exc}", file=sys.stderr, flush=True)
    return leaks


@router.get("/{deck_id}/export/{export_format}")
def export_deck(
    deck_id: str,
    export_format: str,
    user_id: Annotated[str, Depends(get_user_id)],
    svc: Annotated[DeckService, Depends(get_deck_service)],
    llm: Annotated[LLMService, Depends(get_llm_service)],
) -> Response:
    normalized = export_format.lower().strip()
    deck = svc.get_deck(deck_id, user_id)
    if deck is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    if normalized == "html":
        return Response(
            content=deck.html_doc,
            media_type="text/html",
            headers={"Content-Disposition": f'inline; filename="deck-{deck_id}.html"'},
        )

    if normalized == "pptx":
        try:
            slides = _html_to_spec_slides(deck.html_doc, llm)
            out_path = generate_pptx_slides(
                title=f"Deck {deck_id[:8]}",
                slides=slides,
                brand=_brand_from_tokens(deck),
                widget_charts=None,
                pptx_template_path=_resolve_pptx_template_for_deck(deck),
            )
            data = Path(out_path).read_bytes()
            leaks = _check_placeholder_leak(data)
            if leaks:
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "PPTX export contains unresolved placeholders. "
                        "Retry or check template."
                    ),
                )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"PPTX export failed: {exc}"
            ) from exc
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            headers={
                "Content-Disposition": f'attachment; filename="deck-{deck_id}.pptx"',
                "X-Genie-Export-Experimental": "true",
                "X-Genie-Export-Note": _EXPERIMENTAL_HTML_EXPORT_NOTE,
            },
        )

    if normalized == "pdf":
        from services.pdf_export_service import export_deck_html_to_pdf

        try:
            pdf_bytes = export_deck_html_to_pdf(deck.html_doc)
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"PDF export failed: {exc}"
            ) from exc
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="deck-{deck_id}.pdf"'
            },
        )

    if normalized == "google_slides":
        try:
            from vendor.gslides_builder import create_presentation_from_spec  # type: ignore
        except ImportError as exc:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=f"google_slides export unavailable: {exc}",
            ) from exc
        try:
            slides = _html_to_spec_slides(deck.html_doc, llm)
            template_id = deck.google_slides_template_id or None
            kwargs = {
                "title": f"Deck {deck_id[:8]}",
                "slides": slides,
                "theme": "light",
            }
            if template_id:
                kwargs["template_id"] = template_id
            if deck.gslides_file_id:
                kwargs["file_id"] = deck.gslides_file_id
            result = create_presentation_from_spec(**kwargs)
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"google_slides export failed (gcloud auth required): {exc}",
            ) from exc
        url = result.get("url") if isinstance(result, dict) else None
        if not url:
            raise HTTPException(
                status_code=500, detail="google_slides export missing URL in response"
            )
        pres_id = result.get("presentationId")
        if isinstance(pres_id, str) and pres_id:
            try:
                svc.update_gslides_link(deck_id, user_id, pres_id, url)
            except Exception as exc:
                print(
                    f"[gslides] update_link failed: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
        return Response(
            content=json.dumps(
                {
                    "url": url,
                    "presentationId": result.get("presentationId"),
                    "experimental": True,
                    "export_note": _EXPERIMENTAL_HTML_EXPORT_NOTE,
                }
            ),
            media_type="application/json",
            headers={
                "X-Genie-Export-Experimental": "true",
                "X-Genie-Export-Note": _EXPERIMENTAL_HTML_EXPORT_NOTE,
            },
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unknown export format: {export_format}",
    )
