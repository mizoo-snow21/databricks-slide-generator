#!/usr/bin/env python3
"""
Google Slides Builder - Build presentations with proper element management

This script helps create well-formatted Google Slides presentations by:
1. Creating presentations and slides with Databricks templates
2. Adding shapes, text, images, tables, and charts
3. Duplicating slides and managing layouts
4. Replacing text in placeholders and shapes
5. Copying slides between presentations

Usage:
    # Create from Databricks template
    python3 gslides_builder.py create-from-template --title "My Presentation"

    # Add a slide with template layout
    python3 gslides_builder.py add-template-slide --pres-id "PRES_ID" --layout "content_basic"

    # Replace placeholder text
    python3 gslides_builder.py replace-text --pres-id "PRES_ID" --find "{{TITLE}}" --replace "My Title"
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from typing import Dict, List, Optional, Any, Tuple


# =============================================================================
# GCLOUD PATH DISCOVERY
# =============================================================================

_gcloud_path_cache: Optional[str] = None


def find_gcloud() -> Optional[str]:
    """Find gcloud CLI path dynamically."""
    global _gcloud_path_cache

    if _gcloud_path_cache:
        return _gcloud_path_cache

    gcloud_path = shutil.which("gcloud")
    if gcloud_path:
        _gcloud_path_cache = gcloud_path
        return gcloud_path

    common_paths = [
        os.path.expanduser("~/google-cloud-sdk/bin/gcloud"),
        os.path.expanduser("~/Downloads/google-cloud-sdk/bin/gcloud"),
        "/usr/local/bin/gcloud",
        "/opt/homebrew/bin/gcloud",
        "/opt/homebrew/share/google-cloud-sdk/bin/gcloud",
        "/usr/bin/gcloud",
        "/opt/google-cloud-sdk/bin/gcloud",
    ]

    for path in common_paths:
        if os.path.exists(path):
            _gcloud_path_cache = path
            return path

    return None


def get_gcloud_path() -> str:
    """Get gcloud CLI path, raising an error if not found."""
    gcloud_path = find_gcloud()
    if not gcloud_path:
        print("ERROR: gcloud CLI not found.", file=sys.stderr)
        print("Please install Google Cloud SDK:", file=sys.stderr)
        print("  brew install --cask google-cloud-sdk", file=sys.stderr)
        sys.exit(1)
    return gcloud_path


QUOTA_PROJECT = "gcp-sandbox-field-eng"

import time as _time

_access_token_cache: Optional[Tuple[str, float]] = None
_TOKEN_TTL_SECONDS = 50 * 60  # 50 minutes (ADC tokens expire at 60)
_presentation_cache: Dict[str, Dict] = {}


def get_access_token() -> str:
    """Get access token from gcloud ADC (cached with 50-minute TTL)."""
    global _access_token_cache
    if _access_token_cache:
        token, ts = _access_token_cache
        if _time.time() - ts < _TOKEN_TTL_SECONDS:
            return token
    gcloud_path = get_gcloud_path()
    result = subprocess.run(
        [gcloud_path, "auth", "application-default", "print-access-token"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to get access token: {result.stderr}")
    token = result.stdout.strip()
    _access_token_cache = (token, _time.time())
    return token


def _invalidate_presentation_cache(pres_id: str) -> None:
    """Invalidate cached presentation data after mutations."""
    _presentation_cache.pop(pres_id, None)

# EMU (English Metric Units) conversion
# 1 inch = 914400 EMU, 1 pt = 12700 EMU
EMU_PER_INCH = 914400
EMU_PER_PT = 12700

# Standard slide dimensions for Databricks Corporate Template (13.333" x 7.5" for 16:9)
SLIDE_WIDTH_EMU = 12192000  # 13.333 inches
SLIDE_HEIGHT_EMU = 6858000  # 7.5 inches

# =============================================================================
# SPATIAL AWARENESS - Slide Layout Constants (in inches)
# =============================================================================
# Databricks Corporate Template: 13.333" x 7.5" (16:9 aspect ratio)
SLIDE_WIDTH = 13.333
SLIDE_HEIGHT = 7.5

# Margins and safe areas
MARGIN_LEFT = 0.667
MARGIN_RIGHT = 0.667
MARGIN_TOP = 0.667
MARGIN_BOTTOM = 0.667

# Content area (accounting for margins)
CONTENT_LEFT = MARGIN_LEFT
CONTENT_TOP = MARGIN_TOP
CONTENT_WIDTH = SLIDE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT  # ~12.0 inches
CONTENT_HEIGHT = SLIDE_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM  # ~6.167 inches

# Title area (when title placeholder is present)
TITLE_HEIGHT = 1.0  # Typical title placeholder height
BODY_TOP = MARGIN_TOP + TITLE_HEIGHT + 0.333  # Body starts below title
BODY_HEIGHT = CONTENT_HEIGHT - TITLE_HEIGHT - 0.333  # Remaining height for body

# Dark slide body area (Databricks dark templates have different content area)
# Content starts lower on dark slides due to graphical header elements
DARK_BODY_TOP = 3.0  # Dark slides content starts lower
DARK_BODY_HEIGHT = SLIDE_HEIGHT - DARK_BODY_TOP - MARGIN_BOTTOM  # ~3.833 inches

# Predefined positions (x, y, width, height) for common placements
POSITIONS = {
    # Full content area
    "full": (CONTENT_LEFT, BODY_TOP, CONTENT_WIDTH, BODY_HEIGHT),
    "full_no_title": (CONTENT_LEFT, CONTENT_TOP, CONTENT_WIDTH, CONTENT_HEIGHT),

    # Horizontal thirds
    "left_third": (CONTENT_LEFT, BODY_TOP, CONTENT_WIDTH / 3 - 0.15, BODY_HEIGHT),
    "center_third": (CONTENT_LEFT + CONTENT_WIDTH / 3, BODY_TOP, CONTENT_WIDTH / 3 - 0.15, BODY_HEIGHT),
    "right_third": (CONTENT_LEFT + 2 * CONTENT_WIDTH / 3, BODY_TOP, CONTENT_WIDTH / 3 - 0.15, BODY_HEIGHT),

    # Horizontal halves
    "left_half": (CONTENT_LEFT, BODY_TOP, CONTENT_WIDTH / 2 - 0.15, BODY_HEIGHT),
    "right_half": (CONTENT_LEFT + CONTENT_WIDTH / 2, BODY_TOP, CONTENT_WIDTH / 2 - 0.15, BODY_HEIGHT),

    # Vertical halves
    "top_half": (CONTENT_LEFT, BODY_TOP, CONTENT_WIDTH, BODY_HEIGHT / 2 - 0.15),
    "bottom_half": (CONTENT_LEFT, BODY_TOP + BODY_HEIGHT / 2, CONTENT_WIDTH, BODY_HEIGHT / 2 - 0.15),

    # Quadrants
    "top_left": (CONTENT_LEFT, BODY_TOP, CONTENT_WIDTH / 2 - 0.15, BODY_HEIGHT / 2 - 0.15),
    "top_right": (CONTENT_LEFT + CONTENT_WIDTH / 2, BODY_TOP, CONTENT_WIDTH / 2 - 0.15, BODY_HEIGHT / 2 - 0.15),
    "bottom_left": (CONTENT_LEFT, BODY_TOP + BODY_HEIGHT / 2, CONTENT_WIDTH / 2 - 0.15, BODY_HEIGHT / 2 - 0.15),
    "bottom_right": (CONTENT_LEFT + CONTENT_WIDTH / 2, BODY_TOP + BODY_HEIGHT / 2, CONTENT_WIDTH / 2 - 0.15, BODY_HEIGHT / 2 - 0.15),

    # Centered elements (various sizes)
    "center_large": (1.333, BODY_TOP, 10.667, BODY_HEIGHT),
    "center_medium": (2.667, BODY_TOP + 0.667, 8.0, BODY_HEIGHT - 1.333),
    "center_small": (4.0, BODY_TOP + 1.333, 5.333, BODY_HEIGHT - 2.667),

    # Table positions (optimized for readability) - LIGHT slides
    "table_full": (0.667, BODY_TOP, 12.0, 4.0),
    "table_left": (0.667, BODY_TOP, 5.667, 4.0),
    "table_right": (7.0, BODY_TOP, 5.667, 4.0),

    # Table positions for DARK slides (content starts lower)
    "table_full_dark": (0.667, DARK_BODY_TOP, 12.0, 3.333),
    "table_left_dark": (0.667, DARK_BODY_TOP, 5.667, 3.333),
    "table_right_dark": (7.0, DARK_BODY_TOP, 5.667, 3.333),

    # Chart positions
    "chart_full": (1.0, BODY_TOP + 0.333, 11.333, 4.333),
    "chart_left": (0.667, BODY_TOP, 6.0, 4.667),
    "chart_right": (6.667, BODY_TOP, 6.0, 4.667),

    # Chart positions for DARK slides
    "chart_full_dark": (1.0, DARK_BODY_TOP, 11.333, 3.667),
    "chart_left_dark": (0.667, DARK_BODY_TOP, 6.0, 3.667),
    "chart_right_dark": (6.667, DARK_BODY_TOP, 6.0, 3.667),

    # Image positions
    "image_left": (0.667, BODY_TOP, 5.333, 4.667),
    "image_right": (7.333, BODY_TOP, 5.333, 4.667),
    "image_center": (3.333, BODY_TOP, 6.667, 4.667),
    "image_background": (0, 0, SLIDE_WIDTH, SLIDE_HEIGHT),

    # Text box positions
    "text_title_area": (CONTENT_LEFT, MARGIN_TOP, CONTENT_WIDTH, TITLE_HEIGHT),
    "text_subtitle": (CONTENT_LEFT, MARGIN_TOP + TITLE_HEIGHT, CONTENT_WIDTH, 0.667),
    "text_footer": (CONTENT_LEFT, SLIDE_HEIGHT - 1.0, CONTENT_WIDTH, 0.667),
    "text_caption": (CONTENT_LEFT, SLIDE_HEIGHT - 1.333, CONTENT_WIDTH, 1.0),
}

# Common element sizes
SIZES = {
    "icon_small": (0.667, 0.667),
    "icon_medium": (1.333, 1.333),
    "icon_large": (2.0, 2.0),
    "logo_small": (2.0, 0.667),
    "logo_medium": (3.333, 1.067),
    "logo_large": (4.667, 1.6),
}

# Predefined layouts (generic Google Slides)
LAYOUTS = {
    "BLANK": "BLANK",
    "TITLE": "TITLE",
    "TITLE_AND_BODY": "TITLE_AND_BODY",
    "TITLE_AND_TWO_COLUMNS": "TITLE_AND_TWO_COLUMNS",
    "TITLE_ONLY": "TITLE_ONLY",
    "SECTION_HEADER": "SECTION_HEADER",
    "ONE_COLUMN_TEXT": "ONE_COLUMN_TEXT",
    "MAIN_POINT": "MAIN_POINT",
    "BIG_NUMBER": "BIG_NUMBER",
    "CAPTION_ONLY": "CAPTION_ONLY",
}

# Databricks Corporate Template
DATABRICKS_TEMPLATE_ID = "1UYg8OmucFn47YtoUU5duPL-skAHyaj6iKDnJHDB8FXU"

# Databricks Corporate brand colors (RGB 0-1 scale)
# Primary palette from the corporate template
DATABRICKS_COLORS = {
    "red": {"red": 1.0, "green": 0.212, "blue": 0.125},         # #FF3620 - Primary red
    "dark_red": {"red": 0.596, "green": 0.063, "blue": 0.165},  # #98102A - Dark red
    "dark_teal": {"red": 0.106, "green": 0.188, "blue": 0.216}, # #1B3037 - Primary dark (text, bg)
    "teal": {"red": 0.106, "green": 0.318, "blue": 0.380},      # #1B5161 - Primary teal
    "muted_teal": {"red": 0.384, "green": 0.529, "blue": 0.576},# #618793 - Muted teal
    "light_teal": {"red": 0.624, "green": 0.718, "blue": 0.745},# #9EB7BE - Light teal (captions)
    "slate": {"red": 0.627, "green": 0.667, "blue": 0.733},     # #A0ABBE - Slate gray
    "green": {"red": 0.0, "green": 0.702, "blue": 0.471},       # #00B378 - Accent green
    "yellow": {"red": 1.0, "green": 0.671, "blue": 0.0},        # #FFAB00 - Accent yellow
    "white": {"red": 1.0, "green": 1.0, "blue": 1.0},
    "light_gray": {"red": 0.945, "green": 0.945, "blue": 0.945},# #F1F1F1
    "gray": {"red": 0.6, "green": 0.6, "blue": 0.6},
}

# Databricks Corporate Template Layouts - Light Theme (white background)
# Layout IDs from template 1UYg8OmucFn47YtoUU5duPL-skAHyaj6iKDnJHDB8FXU
DATABRICKS_LAYOUTS_LIGHT = {
    # Title slides
    "title": "p61",                          # Title Slide (dark bg with hexagon pattern)
    "title_alt": "p59",                      # Corporate Theme (dark cover, no placeholders)

    # Content layouts (white background)
    "content_basic": "p64",                  # Title and Content
    "content_subtitle": "p65",              # Title, Subtitle and Content
    "content_2col": "p66",                   # Two Column
    "content_3col": "p67",                   # Three Column
    "content_2col_box": "p68",              # Two Column Box
    "content_3box": "p69",                   # Three Box
    "content_4box": "p70",                   # Four Box
    "title_only": "p63",                     # Title Only (for custom content)

    # Section breaks / headlines (dark background with hexagon pattern)
    "section_break_1": "p62",               # Headline 01
    "section_break_2": "p75",               # Headline 02
    "section_break_3": "p76",               # 1_Headline 01 (with photo)
    "section_break_4": "p77",               # 2_Headline 01 (with photo)
    "section_break_5": "p78",               # 3_Headline 01 (with photo)
    "section_break_6": "p84",               # Section Divider 01

    # Quote layouts
    "quote_dark": "p71",                     # Quote Dark
    "quote_dark_2": "p72",                   # 1_Quote Dark (variant)
    "quote_dark_3": "p73",                   # 2_Quote Dark (variant)
    "quote_white": "p74",                    # Quote White

    # Dark content layouts
    "content_basic_dark": "p80",            # Title and Content Dark
    "title_dark": "p81",                     # Title Dark
    "headline_04": "p83",                    # Headline 04

    # Special layouts
    "blank": "p82",                          # Blank White
    "power_statement": "p75",               # Intentional alias: same layout as section_break_2 (Headline 02), used for bold statement slides
    "closing": "p60",                        # 1_Corporate Theme (dark cover)
    "closing_alt": "p59",                    # Intentional alias: same layout as title_alt (Corporate Theme), used as alternative closing
}

# Databricks Corporate Template Layouts - Dark Theme
DATABRICKS_LAYOUTS_DARK = {
    "title": "p61",                          # Title Slide (same - already dark)
    "content_basic": "p80",                  # Title and Content Dark
    "title_only": "p81",                     # Title Dark
    "section_break_1": "p62",               # Headline 01
    "section_break_2": "p84",               # Section Divider 01
    "quote": "p71",                          # Quote Dark
    "blank": "p82",                          # Blank White
    "closing": "p60",                        # 1_Corporate Theme
}


def api_call(method: str, url: str, data: Optional[Dict] = None) -> Dict:
    """Make an API call using urllib (no subprocess overhead).

    Raises RuntimeError on HTTP 4xx/5xx responses so callers don't silently
    consume error bodies.  Stale-token 401s invalidate the token cache and
    retry once.
    """
    import urllib.request
    import urllib.error

    token = get_access_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "x-goog-user-project": QUOTA_PROJECT,
        "Content-Type": "application/json",
    }

    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        if e.code == 401:
            global _access_token_cache
            _access_token_cache = None
            token = get_access_token()
            headers["Authorization"] = f"Bearer {token}"
            req = urllib.request.Request(url, data=body, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req) as resp:
                    raw = resp.read().decode("utf-8")
            except urllib.error.HTTPError as e2:
                raise RuntimeError(f"API call failed (HTTP {e2.code}): {e2.read().decode('utf-8')}")
        else:
            raise RuntimeError(f"API call failed (HTTP {e.code}): {error_body}")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def generate_id() -> str:
    """Generate a unique object ID."""
    return f"obj_{uuid.uuid4().hex[:12]}"


def create_presentation(title: str) -> str:
    """Create a new Google Slides presentation and return its ID."""
    response = api_call(
        "POST",
        "https://slides.googleapis.com/v1/presentations",
        {"title": title}
    )

    if "error" in response:
        raise RuntimeError(f"Failed to create presentation: {response['error']['message']}")

    return response["presentationId"]


def get_presentation(pres_id: str) -> Dict:
    """Get full presentation structure (cached, invalidated on mutation)."""
    if pres_id in _presentation_cache:
        return _presentation_cache[pres_id]
    result = api_call("GET", f"https://slides.googleapis.com/v1/presentations/{pres_id}")
    _presentation_cache[pres_id] = result
    return result


def batch_update(pres_id: str, requests: List[Dict]) -> Dict:
    """Execute a batchUpdate on the presentation (invalidates cache)."""
    _invalidate_presentation_cache(pres_id)
    return api_call(
        "POST",
        f"https://slides.googleapis.com/v1/presentations/{pres_id}:batchUpdate",
        {"requests": requests}
    )


def get_slide_ids(pres_id: str) -> List[str]:
    """Get list of slide IDs in presentation order."""
    pres = get_presentation(pres_id)
    return [slide["objectId"] for slide in pres.get("slides", [])]


def get_slide_elements(pres_id: str, page_id: str) -> List[Dict]:
    """Get all elements on a specific slide."""
    pres = get_presentation(pres_id)
    for slide in pres.get("slides", []):
        if slide["objectId"] == page_id:
            return slide.get("pageElements", [])
    return []


def find_placeholder(pres_id: str, page_id: str, placeholder_type: str) -> Optional[str]:
    """Find a placeholder element by type (TITLE, SUBTITLE, BODY, etc.)."""
    elements = get_slide_elements(pres_id, page_id)
    for elem in elements:
        shape = elem.get("shape", {})
        placeholder = shape.get("placeholder", {})
        if placeholder.get("type") == placeholder_type:
            return elem["objectId"]
    return None


def get_all_placeholders(pres_id: str, page_id: str) -> List[Dict]:
    """Get all placeholder elements on a slide with their info."""
    elements = get_slide_elements(pres_id, page_id)
    placeholders = []
    for elem in elements:
        shape = elem.get("shape", {})
        placeholder = shape.get("placeholder", {})
        if placeholder:
            placeholders.append({
                "objectId": elem["objectId"],
                "type": placeholder.get("type"),
                "index": placeholder.get("index"),
                "parentObjectId": placeholder.get("parentObjectId")
            })
    return placeholders


def get_text_content(pres_id: str, shape_id: str) -> str:
    """Get the text content of a shape."""
    pres = get_presentation(pres_id)
    for slide in pres.get("slides", []):
        for elem in slide.get("pageElements", []):
            if elem.get("objectId") == shape_id:
                shape = elem.get("shape", {})
                text = shape.get("text", {})
                content = ""
                for text_elem in text.get("textElements", []):
                    text_run = text_elem.get("textRun", {})
                    content += text_run.get("content", "")
                return content.strip()
    return ""


def inches_to_emu(inches: float) -> int:
    """Convert inches to EMU."""
    return int(inches * EMU_PER_INCH)


def pt_to_emu(pt: float) -> int:
    """Convert points to EMU."""
    return int(pt * EMU_PER_PT)


def get_position(position_name: str) -> Tuple[float, float, float, float]:
    """
    Get predefined position coordinates by name.

    Args:
        position_name: Name from POSITIONS dict (e.g., 'left_half', 'table_full')

    Returns:
        Tuple of (x, y, width, height) in inches

    Available positions:
        Full area: full, full_no_title
        Thirds: left_third, center_third, right_third
        Halves: left_half, right_half, top_half, bottom_half
        Quadrants: top_left, top_right, bottom_left, bottom_right
        Centered: center_large, center_medium, center_small
        Tables: table_full, table_left, table_right
        Charts: chart_full, chart_left, chart_right
        Images: image_left, image_right, image_center, image_background
        Text: text_title_area, text_subtitle, text_footer, text_caption
    """
    if position_name not in POSITIONS:
        available = ", ".join(sorted(POSITIONS.keys()))
        raise ValueError(f"Unknown position '{position_name}'. Available: {available}")
    return POSITIONS[position_name]


def get_size(size_name: str) -> Tuple[float, float]:
    """
    Get predefined size by name.

    Args:
        size_name: Name from SIZES dict (e.g., 'icon_small', 'logo_medium')

    Returns:
        Tuple of (width, height) in inches
    """
    if size_name not in SIZES:
        available = ", ".join(sorted(SIZES.keys()))
        raise ValueError(f"Unknown size '{size_name}'. Available: {available}")
    return SIZES[size_name]


def calculate_grid_position(
    row: int,
    col: int,
    rows: int,
    cols: int,
    padding: float = 0.1
) -> Tuple[float, float, float, float]:
    """
    Calculate position for an element in a grid layout.

    Args:
        row: Row index (0-based)
        col: Column index (0-based)
        rows: Total number of rows
        cols: Total number of columns
        padding: Padding between cells in inches

    Returns:
        Tuple of (x, y, width, height) in inches
    """
    cell_width = (CONTENT_WIDTH - (cols - 1) * padding) / cols
    cell_height = (BODY_HEIGHT - (rows - 1) * padding) / rows

    x = CONTENT_LEFT + col * (cell_width + padding)
    y = BODY_TOP + row * (cell_height + padding)

    return (x, y, cell_width, cell_height)


def list_positions() -> List[str]:
    """Return list of all available position names."""
    return sorted(POSITIONS.keys())


def list_sizes() -> List[str]:
    """Return list of all available size names."""
    return sorted(SIZES.keys())


# =============================================================================
# SLIDE OPERATIONS
# =============================================================================

def create_from_template(
    title: str,
    template_id: str = DATABRICKS_TEMPLATE_ID,
    delete_sample_slides: bool = True
) -> str:
    """
    Create a new presentation by copying a template.

    Args:
        title: Title for the new presentation
        template_id: Source template presentation ID
        delete_sample_slides: Whether to delete sample slides from template

    Returns:
        New presentation ID
    """
    # Copy the template using Drive API
    # Explicitly set parents to ["root"] so the copy lands in the user's
    # My Drive root instead of inheriting the template's parent folder.
    response = api_call(
        "POST",
        f"https://www.googleapis.com/drive/v3/files/{template_id}/copy",
        {"name": title, "parents": ["root"]}
    )

    if "error" in response:
        raise RuntimeError(f"Failed to copy template: {response['error']['message']}")

    new_pres_id = response["id"]

    # Optionally delete sample slides (keep only masters/layouts)
    if delete_sample_slides:
        slides = get_slide_ids(new_pres_id)
        if len(slides) > 1:
            requests = [{"deleteObject": {"objectId": sid}} for sid in slides[:-1]]
            batch_update(new_pres_id, requests)

    return new_pres_id


def add_slide(
    pres_id: str,
    layout: str = "BLANK",
    insertion_index: Optional[int] = None,
    page_id: Optional[str] = None,
    layout_id: Optional[str] = None
) -> Dict:
    """
    Add a new slide to the presentation.

    Args:
        pres_id: Presentation ID
        layout: Predefined layout type (BLANK, TITLE, TITLE_AND_BODY, etc.)
                Used only if layout_id is not provided.
        insertion_index: Where to insert (None = end)
        page_id: Optional custom page ID
        layout_id: Custom layout object ID (for template layouts).
                   If provided, overrides the 'layout' parameter.

    Returns:
        API response with created slide info
    """
    page_id = page_id or generate_id()

    # Build the slide layout reference
    if layout_id:
        # Use custom layout ID (e.g., from Databricks template)
        slide_layout_ref = {"layoutId": layout_id}
    else:
        # Use predefined layout
        slide_layout_ref = {"predefinedLayout": layout}

    request = {
        "createSlide": {
            "objectId": page_id,
            "slideLayoutReference": slide_layout_ref
        }
    }

    if insertion_index is not None:
        request["createSlide"]["insertionIndex"] = insertion_index

    result = batch_update(pres_id, [request])

    if "error" not in result:
        result["pageId"] = page_id

    return result


def add_slide_from_template(
    pres_id: str,
    layout_name: str,
    theme: str = "light",
    insertion_index: Optional[int] = None,
    page_id: Optional[str] = None
) -> Dict:
    """
    Add a slide using a Databricks template layout by name.

    Args:
        pres_id: Presentation ID (must be created from Databricks template)
        layout_name: Layout name (e.g., 'title', 'content_basic', 'content_2col')
        theme: 'light' or 'dark'
        insertion_index: Where to insert (None = end)
        page_id: Optional custom page ID

    Available layout names (light theme):
        Title slides: title, title_alt
        Content (white bg): content_basic, content_subtitle, content_2col,
                 content_3col, content_2col_box, content_3box, content_4box, title_only
        Content (dark bg): content_basic_dark, title_dark, headline_04
        Section breaks: section_break_1 through section_break_6
        Quotes: quote_dark, quote_dark_2, quote_dark_3, quote_white
        Special: blank, power_statement, closing, closing_alt

    Returns:
        API response with created slide info
    """
    layouts = DATABRICKS_LAYOUTS_DARK if theme == "dark" else DATABRICKS_LAYOUTS_LIGHT

    if layout_name not in layouts:
        available = ", ".join(sorted(layouts.keys()))
        raise ValueError(f"Unknown layout '{layout_name}'. Available: {available}")

    layout_id = layouts[layout_name]
    return add_slide(pres_id, layout_id=layout_id, insertion_index=insertion_index, page_id=page_id)


def list_layouts(pres_id: str) -> List[Dict]:
    """Get all available layouts in a presentation."""
    pres = get_presentation(pres_id)
    layouts = []
    for layout in pres.get("layouts", []):
        props = layout.get("layoutProperties", {})
        layouts.append({
            "objectId": layout["objectId"],
            "displayName": props.get("displayName", "unnamed"),
            "masterObjectId": props.get("masterObjectId")
        })
    return layouts


def find_layout_by_name(
    pres_id: str,
    name: str,
    fuzzy: bool = True,
    preferred_master: Optional[str] = None
) -> Optional[str]:
    """
    Find a layout ID by its display name.

    Args:
        pres_id: Presentation ID
        name: Layout display name to search for
        fuzzy: If True, matches if name is contained in display name (case-insensitive)
               If False, requires exact match
        preferred_master: If provided, prefer layouts from this master.
                          Use "light" for Databricks light theme (g324ba092b07_3_0)
                          Use "dark" for Databricks dark theme (g324ba092b07_3_358)

    Returns:
        Layout object ID if found, None otherwise
    """
    layouts = list_layouts(pres_id)
    name_lower = name.lower()

    # Resolve preferred master shorthand
    master_ids = {
        "light": "g324ba092b07_3_0",
        "dark": "g324ba092b07_3_358"
    }
    if preferred_master in master_ids:
        preferred_master = master_ids[preferred_master]

    # First try exact match (preferring layouts from specified master)
    exact_matches = []
    for layout in layouts:
        if layout["displayName"].lower() == name_lower:
            exact_matches.append(layout)

    if exact_matches:
        if preferred_master:
            for m in exact_matches:
                if m["masterObjectId"] == preferred_master:
                    return m["objectId"]
        # If preferred_master was specified but not found in exact matches,
        # don't return a layout from the wrong master - fall through to fuzzy
        if not preferred_master:
            return exact_matches[0]["objectId"]

    # If fuzzy matching, try partial match
    if fuzzy:
        fuzzy_matches = []
        for layout in layouts:
            if name_lower in layout["displayName"].lower():
                fuzzy_matches.append(layout)

        if fuzzy_matches:
            if preferred_master:
                for m in fuzzy_matches:
                    if m["masterObjectId"] == preferred_master:
                        return m["objectId"]
            return fuzzy_matches[0]["objectId"]

    return None


# Databricks Corporate Template layout display name mappings
# These map shorthand names to the actual layout display names in the corporate template
DATABRICKS_LAYOUT_NAMES = {
    # Title slides
    "title": "Title Slide",
    "title_alt": "Corporate Theme",

    # Content layouts (white background)
    "content_basic": "Title and Content",
    "content_subtitle": "Title, Subtitle and Content",
    "content_2col": "Two Column",
    "content_3col": "Three Column",
    "content_2col_box": "Two Column Box",
    "content_3box": "Three Box",
    "content_4box": "Four Box",
    "title_only": "Title Only",

    # Section breaks / headlines (dark background)
    "section_break_1": "Headline 01",
    "section_break_2": "Headline 02",
    "section_break_3": "1_Headline 01",
    "section_break_4": "2_Headline 01",
    "section_break_5": "3_Headline 01",
    "section_break_6": "Section Divider 01",

    # Quote layouts
    "quote_dark": "Quote Dark",
    "quote_dark_2": "1_Quote Dark",
    "quote_dark_3": "2_Quote Dark",
    "quote_white": "Quote White",

    # Dark content
    "content_basic_dark": "Title and Content Dark",
    "title_dark": "Title Dark",
    "headline_04": "Headline 04",

    # Special layouts
    "blank": "Blank White",
    "power_statement": "Headline 02",
    "closing": "1_Corporate Theme",
    "closing_alt": "Corporate Theme",
}


def add_template_slide_by_name(
    pres_id: str,
    layout_name: str,
    insertion_index: Optional[int] = None,
    page_id: Optional[str] = None,
    theme: str = "light"
) -> Dict:
    """
    Add a slide using a Databricks template layout by name.

    This function looks up the layout ID dynamically from the presentation,
    which works correctly even when the presentation was copied from a template
    (where layout IDs change but display names stay the same).

    Args:
        pres_id: Presentation ID
        layout_name: Either a key from DATABRICKS_LAYOUT_NAMES or a display name
        insertion_index: Where to insert (None = end)
        page_id: Optional custom page ID
        theme: "light" or "dark" - prefer layouts from this theme's master

    Returns:
        API response with created slide info
    """
    # First check if it's a shorthand name
    search_name = DATABRICKS_LAYOUT_NAMES.get(layout_name, layout_name)

    # Find the layout ID in this presentation, preferring the specified theme
    layout_id = find_layout_by_name(pres_id, search_name, preferred_master=theme)

    if not layout_id:
        # List available layouts in error message
        layouts = list_layouts(pres_id)
        available = [l["displayName"] for l in layouts if not l["displayName"].startswith("Title slide")]
        return {
            "error": {
                "message": f"Layout '{layout_name}' not found. Available layouts: {', '.join(available[:10])}..."
            }
        }

    return add_slide(pres_id, layout_id=layout_id, insertion_index=insertion_index, page_id=page_id)


def duplicate_slide(pres_id: str, page_id: str, new_page_id: Optional[str] = None) -> Dict:
    """
    Duplicate a slide within the same presentation.

    Args:
        pres_id: Presentation ID
        page_id: ID of slide to duplicate
        new_page_id: Optional ID for the new slide

    Returns:
        API response
    """
    new_page_id = new_page_id or generate_id()

    request = {
        "duplicateObject": {
            "objectId": page_id,
            "objectIds": {
                page_id: new_page_id
            }
        }
    }

    result = batch_update(pres_id, [request])
    if "error" not in result:
        result["newPageId"] = new_page_id

    return result


def delete_slide(pres_id: str, page_id: str) -> Dict:
    """Delete a slide from the presentation."""
    request = {
        "deleteObject": {
            "objectId": page_id
        }
    }
    return batch_update(pres_id, [request])


def move_slides(pres_id: str, slide_ids: List[str], insertion_index: int) -> Dict:
    """Move slides to a new position."""
    request = {
        "updateSlidesPosition": {
            "slideObjectIds": slide_ids,
            "insertionIndex": insertion_index
        }
    }
    return batch_update(pres_id, [request])


def set_slide_background(
    pres_id: str,
    page_id: str,
    color: Optional[Dict] = None,
    image_url: Optional[str] = None
) -> Dict:
    """
    Set slide background color or image.

    Args:
        pres_id: Presentation ID
        page_id: Slide ID
        color: RGB color dict {"red": 0-1, "green": 0-1, "blue": 0-1}
        image_url: URL of background image

    Returns:
        API response
    """
    page_properties = {}

    if color:
        page_properties["pageBackgroundFill"] = {
            "solidFill": {
                "color": {"rgbColor": color}
            }
        }
    elif image_url:
        page_properties["pageBackgroundFill"] = {
            "stretchedPictureFill": {
                "contentUrl": image_url
            }
        }

    request = {
        "updatePageProperties": {
            "objectId": page_id,
            "pageProperties": page_properties,
            "fields": "pageBackgroundFill"
        }
    }

    return batch_update(pres_id, [request])


# =============================================================================
# TEXT OPERATIONS
# =============================================================================

def insert_text(pres_id: str, shape_id: str, text: str, index: int = 0) -> Dict:
    """Insert text into a shape or placeholder."""
    request = {
        "insertText": {
            "objectId": shape_id,
            "text": text,
            "insertionIndex": index
        }
    }
    return batch_update(pres_id, [request])


def delete_text(pres_id: str, shape_id: str, start_index: int = 0, end_index: Optional[int] = None) -> Dict:
    """Delete text from a shape."""
    text_range = {"type": "FROM_START_INDEX", "startIndex": start_index}
    if end_index is not None:
        text_range = {
            "type": "FIXED_RANGE",
            "startIndex": start_index,
            "endIndex": end_index
        }

    request = {
        "deleteText": {
            "objectId": shape_id,
            "textRange": text_range
        }
    }
    return batch_update(pres_id, [request])


def replace_all_text(
    pres_id: str,
    find: str,
    replace: str,
    match_case: bool = False,
    page_ids: Optional[List[str]] = None
) -> Dict:
    """
    Replace all occurrences of text across the presentation.

    Args:
        pres_id: Presentation ID
        find: Text to find
        replace: Replacement text
        match_case: Whether to match case
        page_ids: Optional list of page IDs to limit replacement to

    Returns:
        API response with number of occurrences replaced
    """
    request = {
        "replaceAllText": {
            "containsText": {
                "text": find,
                "matchCase": match_case
            },
            "replaceText": replace
        }
    }

    if page_ids:
        request["replaceAllText"]["pageObjectIds"] = page_ids

    return batch_update(pres_id, [request])


def replace_shape_text(
    pres_id: str,
    shape_id: str,
    new_text: str,
    preserve_style: bool = True
) -> Dict:
    """
    Replace all text in a shape with new text.

    Args:
        pres_id: Presentation ID
        shape_id: Shape object ID
        new_text: New text to set
        preserve_style: If True, preserves existing text style (font, size, color)

    Returns:
        API response
    """
    # Check if shape has existing text
    existing_text = get_text_content(pres_id, shape_id)

    requests = []

    # Only delete if there's existing text (avoid error on empty shapes)
    if existing_text:
        requests.append({
            "deleteText": {
                "objectId": shape_id,
                "textRange": {"type": "ALL"}
            }
        })

    # Insert new text
    requests.append({
        "insertText": {
            "objectId": shape_id,
            "text": new_text,
            "insertionIndex": 0
        }
    })

    return batch_update(pres_id, requests)


def set_placeholder_text(pres_id: str, page_id: str, placeholder_type: str, text: str) -> Dict:
    """
    Set text in a placeholder (TITLE, SUBTITLE, BODY).

    Args:
        pres_id: Presentation ID
        page_id: Slide ID
        placeholder_type: TITLE, SUBTITLE, BODY, CENTERED_TITLE
        text: Text to insert

    Returns:
        API response
    """
    shape_id = find_placeholder(pres_id, page_id, placeholder_type)
    if not shape_id:
        raise RuntimeError(f"Placeholder {placeholder_type} not found on slide {page_id}")

    return replace_shape_text(pres_id, shape_id, text)


def update_text_style(
    pres_id: str,
    shape_id: str,
    start_index: int,
    end_index: int,
    bold: Optional[bool] = None,
    italic: Optional[bool] = None,
    underline: Optional[bool] = None,
    strikethrough: Optional[bool] = None,
    font_size: Optional[float] = None,
    font_family: Optional[str] = None,
    foreground_color: Optional[Dict] = None,
    link_url: Optional[str] = None
) -> Dict:
    """Update text style for a range of text."""
    style = {}
    fields = []

    if bold is not None:
        style["bold"] = bold
        fields.append("bold")

    if italic is not None:
        style["italic"] = italic
        fields.append("italic")

    if underline is not None:
        style["underline"] = underline
        fields.append("underline")

    if strikethrough is not None:
        style["strikethrough"] = strikethrough
        fields.append("strikethrough")

    if font_size is not None:
        style["fontSize"] = {"magnitude": font_size, "unit": "PT"}
        fields.append("fontSize")

    if font_family is not None:
        style["fontFamily"] = font_family
        fields.append("fontFamily")

    if foreground_color is not None:
        style["foregroundColor"] = {"opaqueColor": {"rgbColor": foreground_color}}
        fields.append("foregroundColor")

    if link_url is not None:
        style["link"] = {"url": link_url}
        fields.append("link")

    request = {
        "updateTextStyle": {
            "objectId": shape_id,
            "textRange": {
                "type": "FIXED_RANGE",
                "startIndex": start_index,
                "endIndex": end_index
            },
            "style": style,
            "fields": ",".join(fields)
        }
    }

    return batch_update(pres_id, [request])


def create_bullets(
    pres_id: str,
    shape_id: str,
    start_index: int,
    end_index: int,
    preset: str = "BULLET_DISC_CIRCLE_SQUARE"
) -> Dict:
    """Create bullet points in a text range."""
    request = {
        "createParagraphBullets": {
            "objectId": shape_id,
            "textRange": {
                "type": "FIXED_RANGE",
                "startIndex": start_index,
                "endIndex": end_index
            },
            "bulletPreset": preset
        }
    }
    return batch_update(pres_id, [request])


# =============================================================================
# SHAPE OPERATIONS
# =============================================================================

def create_shape(
    pres_id: str,
    page_id: str,
    shape_type: str,
    x: float,
    y: float,
    width: float,
    height: float,
    shape_id: Optional[str] = None
) -> Dict:
    """
    Create a shape on a slide.

    Args:
        pres_id: Presentation ID
        page_id: Slide ID
        shape_type: RECTANGLE, ELLIPSE, TEXT_BOX, etc.
        x, y: Position in inches from top-left
        width, height: Size in inches
        shape_id: Optional custom shape ID

    Returns:
        API response
    """
    shape_id = shape_id or generate_id()

    request = {
        "createShape": {
            "objectId": shape_id,
            "shapeType": shape_type,
            "elementProperties": {
                "pageObjectId": page_id,
                "size": {
                    "width": {"magnitude": inches_to_emu(width), "unit": "EMU"},
                    "height": {"magnitude": inches_to_emu(height), "unit": "EMU"}
                },
                "transform": {
                    "scaleX": 1,
                    "scaleY": 1,
                    "translateX": inches_to_emu(x),
                    "translateY": inches_to_emu(y),
                    "unit": "EMU"
                }
            }
        }
    }

    result = batch_update(pres_id, [request])
    if "error" not in result:
        result["shapeId"] = shape_id

    return result


def create_text_box(
    pres_id: str,
    page_id: str,
    text: str,
    x: float,
    y: float,
    width: float,
    height: float,
    font_size: float = 18,
    bold: bool = False,
    font_color: Optional[Dict] = None,
    text_box_id: Optional[str] = None
) -> Dict:
    """
    Create a text box with text on a slide.

    Args:
        pres_id: Presentation ID
        page_id: Slide ID
        text: Text content
        x, y: Position in inches
        width, height: Size in inches
        font_size: Font size in points
        bold: Whether text is bold
        font_color: Optional RGB color dict
        text_box_id: Optional custom ID

    Returns:
        API response with textBoxId
    """
    text_box_id = text_box_id or generate_id()

    style = {
        "fontSize": {"magnitude": font_size, "unit": "PT"},
        "bold": bold
    }
    fields = ["fontSize", "bold"]

    if font_color:
        style["foregroundColor"] = {"opaqueColor": {"rgbColor": font_color}}
        fields.append("foregroundColor")

    # Create shape and insert text in one batch
    requests = [
        {
            "createShape": {
                "objectId": text_box_id,
                "shapeType": "TEXT_BOX",
                "elementProperties": {
                    "pageObjectId": page_id,
                    "size": {
                        "width": {"magnitude": inches_to_emu(width), "unit": "EMU"},
                        "height": {"magnitude": inches_to_emu(height), "unit": "EMU"}
                    },
                    "transform": {
                        "scaleX": 1,
                        "scaleY": 1,
                        "translateX": inches_to_emu(x),
                        "translateY": inches_to_emu(y),
                        "unit": "EMU"
                    }
                }
            }
        },
        {
            "insertText": {
                "objectId": text_box_id,
                "text": text,
                "insertionIndex": 0
            }
        },
        {
            "updateTextStyle": {
                "objectId": text_box_id,
                "textRange": {"type": "ALL"},
                "style": style,
                "fields": ",".join(fields)
            }
        }
    ]

    result = batch_update(pres_id, requests)
    if "error" not in result:
        result["textBoxId"] = text_box_id

    return result


def update_shape_properties(
    pres_id: str,
    shape_id: str,
    fill_color: Optional[Dict] = None,
    outline_color: Optional[Dict] = None,
    outline_weight: Optional[float] = None
) -> Dict:
    """Update shape fill and outline properties."""
    properties = {}
    fields = []

    if fill_color is not None:
        properties["shapeBackgroundFill"] = {
            "solidFill": {"color": {"rgbColor": fill_color}}
        }
        fields.append("shapeBackgroundFill")

    if outline_color is not None or outline_weight is not None:
        outline = {}
        if outline_color is not None:
            outline["outlineFill"] = {
                "solidFill": {"color": {"rgbColor": outline_color}}
            }
            fields.append("outline.outlineFill")
        if outline_weight is not None:
            outline["weight"] = {"magnitude": outline_weight, "unit": "PT"}
            fields.append("outline.weight")
        properties["outline"] = outline

    request = {
        "updateShapeProperties": {
            "objectId": shape_id,
            "shapeProperties": properties,
            "fields": ",".join(fields)
        }
    }

    return batch_update(pres_id, [request])


# =============================================================================
# IMAGE OPERATIONS
# =============================================================================

def create_image(
    pres_id: str,
    page_id: str,
    image_url: str,
    x: float,
    y: float,
    width: float,
    height: float,
    image_id: Optional[str] = None
) -> Dict:
    """
    Insert an image on a slide.

    Args:
        pres_id: Presentation ID
        page_id: Slide ID
        image_url: URL of the image
        x, y: Position in inches
        width, height: Size in inches
        image_id: Optional custom ID

    Returns:
        API response with imageId
    """
    image_id = image_id or generate_id()

    request = {
        "createImage": {
            "objectId": image_id,
            "url": image_url,
            "elementProperties": {
                "pageObjectId": page_id,
                "size": {
                    "width": {"magnitude": inches_to_emu(width), "unit": "EMU"},
                    "height": {"magnitude": inches_to_emu(height), "unit": "EMU"}
                },
                "transform": {
                    "scaleX": 1,
                    "scaleY": 1,
                    "translateX": inches_to_emu(x),
                    "translateY": inches_to_emu(y),
                    "unit": "EMU"
                }
            }
        }
    }

    result = batch_update(pres_id, [request])
    if "error" not in result:
        result["imageId"] = image_id

    return result


def replace_image(
    pres_id: str,
    image_id: str,
    new_image_url: str
) -> Dict:
    """
    Replace an existing image with a new one.

    Args:
        pres_id: Presentation ID
        image_id: Existing image object ID
        new_image_url: URL of the new image

    Returns:
        API response
    """
    request = {
        "replaceImage": {
            "imageObjectId": image_id,
            "url": new_image_url,
            "imageReplaceMethod": "CENTER_INSIDE"
        }
    }

    return batch_update(pres_id, [request])


# =============================================================================
# TABLE OPERATIONS
# =============================================================================

def create_table(
    pres_id: str,
    page_id: str,
    rows: int,
    cols: int,
    x: float,
    y: float,
    width: float,
    height: float,
    table_id: Optional[str] = None
) -> Dict:
    """
    Create a table on a slide.

    Args:
        pres_id: Presentation ID
        page_id: Slide ID
        rows: Number of rows
        cols: Number of columns
        x, y: Position in inches
        width, height: Size in inches
        table_id: Optional custom ID

    Returns:
        API response with tableId
    """
    table_id = table_id or generate_id()

    request = {
        "createTable": {
            "objectId": table_id,
            "rows": rows,
            "columns": cols,
            "elementProperties": {
                "pageObjectId": page_id,
                "size": {
                    "width": {"magnitude": inches_to_emu(width), "unit": "EMU"},
                    "height": {"magnitude": inches_to_emu(height), "unit": "EMU"}
                },
                "transform": {
                    "scaleX": 1,
                    "scaleY": 1,
                    "translateX": inches_to_emu(x),
                    "translateY": inches_to_emu(y),
                    "unit": "EMU"
                }
            }
        }
    }

    result = batch_update(pres_id, [request])
    if "error" not in result:
        result["tableId"] = table_id

    return result


def fill_table(
    pres_id: str,
    table_id: str,
    data: List[List[str]],
    header_bold: bool = True
) -> Dict:
    """
    Fill a table with data.

    Args:
        pres_id: Presentation ID
        table_id: Table object ID
        data: 2D array of cell values
        header_bold: Bold the first row

    Returns:
        API response
    """
    requests = []

    for row_idx, row in enumerate(data):
        for col_idx, cell_text in enumerate(row):
            if cell_text:
                # Insert text into cell
                requests.append({
                    "insertText": {
                        "objectId": table_id,
                        "cellLocation": {
                            "rowIndex": row_idx,
                            "columnIndex": col_idx
                        },
                        "text": str(cell_text),
                        "insertionIndex": 0
                    }
                })

                # Bold header row
                if header_bold and row_idx == 0:
                    requests.append({
                        "updateTextStyle": {
                            "objectId": table_id,
                            "cellLocation": {
                                "rowIndex": row_idx,
                                "columnIndex": col_idx
                            },
                            "textRange": {"type": "ALL"},
                            "style": {"bold": True},
                            "fields": "bold"
                        }
                    })

    return batch_update(pres_id, requests)


def style_table_header(
    pres_id: str,
    table_id: str,
    cols: int,
    bg_color: Dict = None,
    text_color: Dict = None
) -> Dict:
    """
    Style the header row of a table with background and text color.

    Args:
        pres_id: Presentation ID
        table_id: Table object ID
        cols: Number of columns
        bg_color: Background color (default: Databricks navy)
        text_color: Text color (default: white)

    Returns:
        API response
    """
    if bg_color is None:
        bg_color = DATABRICKS_COLORS["dark_teal"]
    if text_color is None:
        text_color = DATABRICKS_COLORS["white"]

    requests = []

    for col_idx in range(cols):
        # Set background color
        requests.append({
            "updateTableCellProperties": {
                "objectId": table_id,
                "tableRange": {
                    "location": {"rowIndex": 0, "columnIndex": col_idx},
                    "rowSpan": 1,
                    "columnSpan": 1
                },
                "tableCellProperties": {
                    "tableCellBackgroundFill": {
                        "solidFill": {"color": {"rgbColor": bg_color}}
                    }
                },
                "fields": "tableCellBackgroundFill"
            }
        })

        # Set text color to white (or specified color)
        requests.append({
            "updateTextStyle": {
                "objectId": table_id,
                "cellLocation": {"rowIndex": 0, "columnIndex": col_idx},
                "textRange": {"type": "ALL"},
                "style": {
                    "foregroundColor": {"opaqueColor": {"rgbColor": text_color}},
                    "bold": True
                },
                "fields": "foregroundColor,bold"
            }
        })

    return batch_update(pres_id, requests)


def style_table_cell(
    pres_id: str,
    table_id: str,
    row: int,
    col: int,
    bg_color: Optional[Dict] = None,
    bold: Optional[bool] = None,
    font_color: Optional[Dict] = None
) -> Dict:
    """Style a specific table cell."""
    requests = []

    if bg_color:
        requests.append({
            "updateTableCellProperties": {
                "objectId": table_id,
                "tableRange": {
                    "location": {"rowIndex": row, "columnIndex": col},
                    "rowSpan": 1,
                    "columnSpan": 1
                },
                "tableCellProperties": {
                    "tableCellBackgroundFill": {
                        "solidFill": {"color": {"rgbColor": bg_color}}
                    }
                },
                "fields": "tableCellBackgroundFill"
            }
        })

    style = {}
    fields = []
    if bold is not None:
        style["bold"] = bold
        fields.append("bold")
    if font_color:
        style["foregroundColor"] = {"opaqueColor": {"rgbColor": font_color}}
        fields.append("foregroundColor")

    if style:
        requests.append({
            "updateTextStyle": {
                "objectId": table_id,
                "cellLocation": {"rowIndex": row, "columnIndex": col},
                "textRange": {"type": "ALL"},
                "style": style,
                "fields": ",".join(fields)
            }
        })

    return batch_update(pres_id, requests) if requests else {"status": "no_changes"}


def style_table_body_text(
    pres_id: str,
    table_id: str,
    rows: int,
    cols: int,
    text_color: Dict = None,
    start_row: int = 1
) -> Dict:
    """
    Style text color for table body cells (non-header rows).

    This is useful for dark backgrounds where body text needs to be white/light.

    Args:
        pres_id: Presentation ID
        table_id: Table object ID
        rows: Total number of rows in table
        cols: Number of columns
        text_color: Text color (default: white)
        start_row: First row to style (default: 1, skips header)

    Returns:
        API response
    """
    if text_color is None:
        text_color = DATABRICKS_COLORS["white"]

    requests = []

    for row_idx in range(start_row, rows):
        for col_idx in range(cols):
            requests.append({
                "updateTextStyle": {
                    "objectId": table_id,
                    "cellLocation": {"rowIndex": row_idx, "columnIndex": col_idx},
                    "textRange": {"type": "ALL"},
                    "style": {
                        "foregroundColor": {"opaqueColor": {"rgbColor": text_color}}
                    },
                    "fields": "foregroundColor"
                }
            })

    return batch_update(pres_id, requests) if requests else {"status": "no_changes"}


def style_table_for_dark_background(
    pres_id: str,
    table_id: str,
    rows: int,
    cols: int,
    header_bg_color: Dict = None,
    text_color: Dict = None
) -> Dict:
    """
    Style a table for dark slide backgrounds.

    Sets header with Databricks red background and white text,
    and body cells with white text.

    Args:
        pres_id: Presentation ID
        table_id: Table object ID
        rows: Total number of rows
        cols: Number of columns
        header_bg_color: Header background color (default: Databricks red)
        text_color: Text color for all cells (default: white)

    Returns:
        API response
    """
    if header_bg_color is None:
        header_bg_color = DATABRICKS_COLORS["red"]
    if text_color is None:
        text_color = DATABRICKS_COLORS["white"]

    requests = []

    # Style header row with background and white text
    for col_idx in range(cols):
        # Header background
        requests.append({
            "updateTableCellProperties": {
                "objectId": table_id,
                "tableRange": {
                    "location": {"rowIndex": 0, "columnIndex": col_idx},
                    "rowSpan": 1,
                    "columnSpan": 1
                },
                "tableCellProperties": {
                    "tableCellBackgroundFill": {
                        "solidFill": {"color": {"rgbColor": header_bg_color}}
                    }
                },
                "fields": "tableCellBackgroundFill"
            }
        })

        # Header text style (bold + white)
        requests.append({
            "updateTextStyle": {
                "objectId": table_id,
                "cellLocation": {"rowIndex": 0, "columnIndex": col_idx},
                "textRange": {"type": "ALL"},
                "style": {
                    "foregroundColor": {"opaqueColor": {"rgbColor": text_color}},
                    "bold": True
                },
                "fields": "foregroundColor,bold"
            }
        })

    # Style body rows with white text
    for row_idx in range(1, rows):
        for col_idx in range(cols):
            requests.append({
                "updateTextStyle": {
                    "objectId": table_id,
                    "cellLocation": {"rowIndex": row_idx, "columnIndex": col_idx},
                    "textRange": {"type": "ALL"},
                    "style": {
                        "foregroundColor": {"opaqueColor": {"rgbColor": text_color}}
                    },
                    "fields": "foregroundColor"
                }
            })

    return batch_update(pres_id, requests)


# =============================================================================
# CHART OPERATIONS (requires Google Sheets)
# =============================================================================

def create_sheets_chart(
    pres_id: str,
    page_id: str,
    spreadsheet_id: str,
    chart_id: int,
    x: float,
    y: float,
    width: float,
    height: float,
    linked: bool = True,
    obj_id: Optional[str] = None
) -> Dict:
    """
    Embed a chart from Google Sheets.

    Args:
        pres_id: Presentation ID
        page_id: Slide ID
        spreadsheet_id: Google Sheets spreadsheet ID
        chart_id: Chart ID within the spreadsheet
        x, y: Position in inches
        width, height: Size in inches
        linked: If True, chart updates when sheet changes
        obj_id: Optional custom object ID

    Returns:
        API response with chartId
    """
    obj_id = obj_id or generate_id()

    request = {
        "createSheetsChart": {
            "objectId": obj_id,
            "spreadsheetId": spreadsheet_id,
            "chartId": chart_id,
            "linkingMode": "LINKED" if linked else "NOT_LINKED_IMAGE",
            "elementProperties": {
                "pageObjectId": page_id,
                "size": {
                    "width": {"magnitude": inches_to_emu(width), "unit": "EMU"},
                    "height": {"magnitude": inches_to_emu(height), "unit": "EMU"}
                },
                "transform": {
                    "scaleX": 1,
                    "scaleY": 1,
                    "translateX": inches_to_emu(x),
                    "translateY": inches_to_emu(y),
                    "unit": "EMU"
                }
            }
        }
    }

    result = batch_update(pres_id, [request])
    if "error" not in result:
        result["chartId"] = obj_id

    return result


def refresh_chart(pres_id: str, chart_id: str) -> Dict:
    """Refresh a linked Sheets chart."""
    request = {
        "refreshSheetsChart": {
            "objectId": chart_id
        }
    }
    return batch_update(pres_id, [request])


# =============================================================================
# COPY OPERATIONS
# =============================================================================

def copy_presentation(pres_id: str, new_title: str) -> str:
    """
    Copy an entire presentation using Drive API.

    Args:
        pres_id: Source presentation ID
        new_title: Title for the new presentation

    Returns:
        New presentation ID
    """
    # Explicitly set parents to ["root"] so the copy lands in the user's
    # My Drive root instead of inheriting the source file's parent folder.
    response = api_call(
        "POST",
        f"https://www.googleapis.com/drive/v3/files/{pres_id}/copy",
        {"name": new_title, "parents": ["root"]}
    )

    if "error" in response:
        raise RuntimeError(f"Failed to copy presentation: {response['error']['message']}")

    return response["id"]


def import_slides_from_presentation(
    target_pres_id: str,
    source_pres_id: str,
    slide_ids: Optional[List[str]] = None,
    insertion_index: Optional[int] = None
) -> Dict:
    """
    Import slides from another presentation.

    Note: This creates a copy of the source presentation, extracts slides,
    and then deletes unwanted slides. Theme is NOT preserved.

    Args:
        target_pres_id: Destination presentation ID
        source_pres_id: Source presentation ID
        slide_ids: List of slide IDs to import (None = all)
        insertion_index: Where to insert slides (None = end)

    Returns:
        Dict with imported slide IDs
    """
    # Get source presentation structure
    source_pres = get_presentation(source_pres_id)
    source_slides = source_pres.get("slides", [])

    if not source_slides:
        raise RuntimeError("Source presentation has no slides")

    # Filter slides if specific IDs requested
    if slide_ids:
        source_slides = [s for s in source_slides if s["objectId"] in slide_ids]

    # Get target presentation to find insertion point
    target_slides = get_slide_ids(target_pres_id)
    insert_at = insertion_index if insertion_index is not None else len(target_slides)

    # We need to recreate each slide manually since there's no direct import API
    # This is a simplified version - for complex slides, consider Apps Script
    imported_ids = []

    for slide_data in source_slides:
        # Create a blank slide
        new_id = generate_id()
        result = add_slide(target_pres_id, "BLANK", insert_at, new_id)

        if "error" in result:
            continue

        imported_ids.append(new_id)
        insert_at += 1

        # Copy elements (simplified - full copy would need all element types)
        # For complete slide copying, use Apps Script or copy entire presentation

    return {"importedSlideIds": imported_ids, "count": len(imported_ids)}


# =============================================================================
# TEMPLATE UTILITIES
# =============================================================================

def validate_presentation(pres_id: str) -> Dict:
    """
    Validate a presentation for common formatting and layout issues.

    Inspects every slide and element via the Slides API (no visual/thumbnail needed)
    and reports issues such as:
    - Inconsistent text styling (off-by-one endIndex leaving chars unstyled)
    - Elements overlapping each other
    - Text potentially overflowing its container
    - Missing text styles (characters falling back to defaults)
    - Oversized placeholder elements from problematic layouts
    """
    pres = get_presentation(pres_id)
    issues = []
    page_size = pres.get("pageSize", {})
    slide_width_emu = page_size.get("width", {}).get("magnitude", SLIDE_WIDTH_EMU)
    slide_height_emu = page_size.get("height", {}).get("magnitude", SLIDE_HEIGHT_EMU)

    for slide_idx, slide in enumerate(pres.get("slides", [])):
        slide_id = slide["objectId"]
        elements = slide.get("pageElements", [])

        element_bounds = []

        for elem in elements:
            elem_id = elem["objectId"]
            transform = elem.get("transform", {})
            size = elem.get("size", {})

            sx = transform.get("scaleX", 1)
            sy = transform.get("scaleY", 1)
            tx = transform.get("translateX", 0)
            ty = transform.get("translateY", 0)
            w = size.get("width", {}).get("magnitude", 0)
            h = size.get("height", {}).get("magnitude", 0)

            actual_w = abs(w * sx)
            actual_h = abs(h * sy)

            has_text = bool(elem.get("shape", {}).get("text", {}).get("textElements"))
            shape_type = elem.get("shape", {}).get("shapeType", "")
            is_thin = (actual_h < 100000 and actual_w > actual_h * 5) or (actual_w < 100000 and actual_h > actual_w * 5)

            element_bounds.append({
                "id": elem_id,
                "x": tx, "y": ty,
                "w": actual_w, "h": actual_h,
                "right": tx + actual_w,
                "bottom": ty + actual_h,
                "has_text": has_text,
                "is_decorative": is_thin and not has_text,
                "shape_type": shape_type,
            })

            # Check: element extends beyond slide bounds
            if tx + actual_w > slide_width_emu * 1.05 or ty + actual_h > slide_height_emu * 1.05:
                issues.append({
                    "slide": slide_idx + 1,
                    "slide_id": slide_id,
                    "element": elem_id,
                    "severity": "warning",
                    "type": "out_of_bounds",
                    "message": f"Element extends beyond slide bounds (right={tx + actual_w:.0f}, bottom={ty + actual_h:.0f}, slide={slide_width_emu}x{slide_height_emu})"
                })

            # Check: oversized placeholder (common with BIG_NUMBER, MAIN_POINT)
            # Only flag if placeholder covers >95% width AND >70% height (truly full-slide)
            ph_type = elem.get("shape", {}).get("placeholder", {}).get("type")
            oversized_w = slide_width_emu * 0.95
            oversized_h = slide_height_emu * 0.70
            if ph_type and ph_type not in ("TITLE", "CENTERED_TITLE", "SUBTITLE", "BODY") and actual_w > oversized_w and actual_h > oversized_h:
                issues.append({
                    "slide": slide_idx + 1,
                    "slide_id": slide_id,
                    "element": elem_id,
                    "severity": "warning",
                    "type": "oversized_placeholder",
                    "message": f"Placeholder '{ph_type}' is very large ({actual_w:.0f}x{actual_h:.0f} EMU). May overlap custom elements. Consider using TITLE_ONLY layout with custom text boxes."
                })

            # Text style validation
            shape = elem.get("shape", {})
            text_elements = shape.get("text", {}).get("textElements", [])
            if not text_elements:
                continue

            text_runs = [te for te in text_elements if "textRun" in te]
            if not text_runs:
                continue

            full_text = "".join(tr["textRun"]["content"] for tr in text_runs)

            font_sizes_in_element = set()
            for tr in text_runs:
                style = tr["textRun"].get("style", {})
                fs = style.get("fontSize", {}).get("magnitude")
                if fs is not None:
                    font_sizes_in_element.add(fs)

            # Check: inconsistent font sizes within a single text run boundary
            # (detects off-by-one where last char falls back to default size)
            if len(font_sizes_in_element) > 1:
                for i, tr in enumerate(text_runs):
                    content = tr["textRun"]["content"]
                    style = tr["textRun"].get("style", {})
                    fs = style.get("fontSize", {}).get("magnitude")
                    fg = style.get("foregroundColor", {})
                    start = tr.get("startIndex", 0)
                    end = tr.get("endIndex", 0)

                    # Suspicious: a very short run (1-2 chars) with a different size
                    # than its neighbors — classic off-by-one symptom
                    if len(content.rstrip("\n")) <= 2 and len(text_runs) > 1:
                        neighbor_sizes = set()
                        if i > 0:
                            ns = text_runs[i-1]["textRun"].get("style", {}).get("fontSize", {}).get("magnitude")
                            if ns: neighbor_sizes.add(ns)
                        if i < len(text_runs) - 1:
                            ns = text_runs[i+1]["textRun"].get("style", {}).get("fontSize", {}).get("magnitude")
                            if ns: neighbor_sizes.add(ns)

                        if fs and neighbor_sizes and fs not in neighbor_sizes and content.strip():
                            issues.append({
                                "slide": slide_idx + 1,
                                "slide_id": slide_id,
                                "element": elem_id,
                                "severity": "error",
                                "type": "text_style_off_by_one",
                                "message": f"Likely off-by-one: char(s) '{content.rstrip(chr(10))}' at index [{start}:{end}] has fontSize={fs}pt but neighbors use different sizes. This usually means endIndex was wrong when styling.",
                                "text_content": repr(content),
                                "font_size": fs,
                                "index_range": [start, end]
                            })

                    # Suspicious: run has no explicit foregroundColor (empty dict)
                    # meaning it falls back to theme default
                    if not fg.get("opaqueColor") and content.strip():
                        has_styled_neighbors = any(
                            t["textRun"].get("style", {}).get("foregroundColor", {}).get("opaqueColor")
                            for t in text_runs if t is not tr
                        )
                        if has_styled_neighbors:
                            issues.append({
                                "slide": slide_idx + 1,
                                "slide_id": slide_id,
                                "element": elem_id,
                                "severity": "warning",
                                "type": "missing_text_color",
                                "message": f"Text '{content.rstrip(chr(10))}' at [{start}:{end}] has no explicit foregroundColor (uses theme default) while other runs in the same element do. Likely a styling gap.",
                                "text_content": repr(content),
                                "index_range": [start, end]
                            })

            # Check: text might overflow container
            line_count = full_text.count("\n")
            avg_font_size = sum(font_sizes_in_element) / len(font_sizes_in_element) if font_sizes_in_element else 14
            estimated_text_height_emu = line_count * avg_font_size * 12700 * 1.4  # pt to EMU with line spacing
            if actual_h > 0 and estimated_text_height_emu > actual_h * 1.1:
                issues.append({
                    "slide": slide_idx + 1,
                    "slide_id": slide_id,
                    "element": elem_id,
                    "severity": "warning",
                    "type": "text_overflow",
                    "message": f"Text may overflow container: ~{line_count} lines at ~{avg_font_size:.0f}pt needs ~{estimated_text_height_emu:.0f} EMU but container height is {actual_h:.0f} EMU.",
                    "line_count": line_count,
                    "container_height_emu": actual_h
                })

        # Check: overlapping elements
        for i, a in enumerate(element_bounds):
            for j, b in enumerate(element_bounds):
                if j <= i:
                    continue
                if (a["x"] < b["right"] and a["right"] > b["x"] and
                    a["y"] < b["bottom"] and a["bottom"] > b["y"]):
                    overlap_w = min(a["right"], b["right"]) - max(a["x"], b["x"])
                    overlap_h = min(a["bottom"], b["bottom"]) - max(a["y"], b["y"])
                    overlap_area = overlap_w * overlap_h
                    min_area = min(a["w"] * a["h"], b["w"] * b["h"])
                    if min_area <= 0:
                        continue

                    # Decorative shape (accent bar/line) overlapping a text element = error
                    deco, txt = None, None
                    if a["is_decorative"] and b["has_text"]:
                        deco, txt = a, b
                    elif b["is_decorative"] and a["has_text"]:
                        deco, txt = b, a

                    if deco and txt and overlap_area / min_area > 0.1:
                        issues.append({
                            "slide": slide_idx + 1,
                            "slide_id": slide_id,
                            "severity": "error",
                            "type": "decorative_overlaps_text",
                            "message": f"Decorative element '{deco['id']}' overlaps text element '{txt['id']}'. The accent bar/line is positioned within the text area. Move it below or above the text content.",
                            "elements": [deco["id"], txt["id"]],
                            "decorative_y": deco["y"],
                            "text_bottom": txt["bottom"],
                        })
                    elif overlap_area / min_area > 0.3:
                        issues.append({
                            "slide": slide_idx + 1,
                            "slide_id": slide_id,
                            "severity": "warning",
                            "type": "element_overlap",
                            "message": f"Elements '{a['id']}' and '{b['id']}' overlap significantly ({overlap_area / min_area:.0%} of smaller element).",
                            "elements": [a["id"], b["id"]]
                        })

    error_count = sum(1 for i in issues if i["severity"] == "error")
    warning_count = sum(1 for i in issues if i["severity"] == "warning")

    return {
        "presentation_id": pres_id,
        "slide_count": len(pres.get("slides", [])),
        "total_issues": len(issues),
        "errors": error_count,
        "warnings": warning_count,
        "status": "PASS" if error_count == 0 else "FAIL",
        "issues": issues
    }


def auto_fix_presentation(pres_id: str) -> Dict:
    """
    Automatically fix common validation issues in a presentation.

    Runs validate_presentation, then applies fixes for:
    - text_style_off_by_one: Re-applies a uniform base style with type=ALL on the affected element
    - decorative_overlaps_text: Deletes the decorative element and recreates it below the text
    - text_overflow: Reduces font size by 2pt increments until estimated height fits

    Returns a summary of fixes applied and any remaining issues.
    """
    validation = validate_presentation(pres_id)
    issues = validation.get("issues", [])
    if not issues:
        return {"status": "CLEAN", "fixes_applied": 0, "message": "No issues to fix"}

    fixes_applied = 0
    fix_log = []

    pres = get_presentation(pres_id)
    slides_by_id = {s["objectId"]: s for s in pres.get("slides", [])}

    off_by_one_elements = set()
    for issue in issues:
        if issue["type"] == "text_style_off_by_one":
            off_by_one_elements.add((issue["slide_id"], issue["element"]))

    for slide_id, elem_id in off_by_one_elements:
        slide = slides_by_id.get(slide_id)
        if not slide:
            continue
        elem = None
        for pe in slide.get("pageElements", []):
            if pe["objectId"] == elem_id:
                elem = pe
                break
        if not elem:
            continue

        text_elements = elem.get("shape", {}).get("text", {}).get("textElements", [])
        text_runs = [te for te in text_elements if "textRun" in te]
        if not text_runs:
            continue

        size_counts: Dict[float, int] = {}
        for tr in text_runs:
            fs = tr["textRun"].get("style", {}).get("fontSize", {}).get("magnitude")
            content = tr["textRun"]["content"]
            if fs is not None:
                size_counts[fs] = size_counts.get(fs, 0) + len(content)

        if not size_counts:
            continue
        dominant_size = max(size_counts, key=size_counts.get)

        dominant_color = None
        for tr in text_runs:
            style = tr["textRun"].get("style", {})
            fg = style.get("foregroundColor", {}).get("opaqueColor", {}).get("rgbColor")
            fs = style.get("fontSize", {}).get("magnitude")
            if fg and fs == dominant_size:
                dominant_color = fg
                break

        style_update: Dict[str, Any] = {
            "fontSize": {"magnitude": dominant_size, "unit": "PT"}
        }
        fields = "fontSize"
        if dominant_color:
            style_update["foregroundColor"] = {"opaqueColor": {"rgbColor": dominant_color}}
            fields += ",foregroundColor"

        try:
            batch_update(pres_id, [{
                "updateTextStyle": {
                    "objectId": elem_id,
                    "textRange": {"type": "ALL"},
                    "style": style_update,
                    "fields": fields
                }
            }])
            fixes_applied += 1
            fix_log.append(f"Fixed off-by-one on element {elem_id} (slide {slide_id}): applied {dominant_size}pt base style")
        except Exception as e:
            fix_log.append(f"Failed to fix off-by-one on {elem_id}: {e}")

    for issue in issues:
        if issue["type"] == "decorative_overlaps_text":
            deco_id = issue.get("elements", [None, None])[0]
            text_bottom = issue.get("text_bottom", 0)
            if not deco_id or not text_bottom:
                continue

            slide_id = issue["slide_id"]
            slide = slides_by_id.get(slide_id)
            if not slide:
                continue

            deco_elem = None
            for pe in slide.get("pageElements", []):
                if pe["objectId"] == deco_id:
                    deco_elem = pe
                    break
            if not deco_elem:
                continue

            deco_size = deco_elem.get("size", {})
            deco_w = deco_size.get("width", {}).get("magnitude", 0)
            deco_h = deco_size.get("height", {}).get("magnitude", 0)
            deco_transform = deco_elem.get("transform", {})
            deco_x = deco_transform.get("translateX", 0)
            deco_fill = deco_elem.get("shape", {}).get("shapeProperties", {}).get("shapeBackgroundFill", {})

            new_y = text_bottom + 50000

            try:
                new_id = generate_id()
                requests = [
                    {"deleteObject": {"objectId": deco_id}},
                    {
                        "createShape": {
                            "objectId": new_id,
                            "shapeType": "RECTANGLE",
                            "elementProperties": {
                                "pageObjectId": slide_id,
                                "size": {
                                    "width": {"magnitude": deco_w, "unit": "EMU"},
                                    "height": {"magnitude": deco_h, "unit": "EMU"}
                                },
                                "transform": {
                                    "scaleX": 1, "scaleY": 1,
                                    "translateX": deco_x,
                                    "translateY": new_y,
                                    "unit": "EMU"
                                }
                            }
                        }
                    }
                ]
                batch_update(pres_id, requests)

                shape_props: Dict[str, Any] = {
                    "outline": {"propertyState": "NOT_RENDERED"}
                }
                fill_solid = deco_fill.get("solidFill", {})
                if fill_solid:
                    shape_props["shapeBackgroundFill"] = {"solidFill": fill_solid}

                batch_update(pres_id, [{
                    "updateShapeProperties": {
                        "objectId": new_id,
                        "shapeProperties": shape_props,
                        "fields": "outline,shapeBackgroundFill"
                    }
                }])
                fixes_applied += 1
                fix_log.append(f"Moved decorative element below text on slide {issue['slide']} (new y={new_y})")
            except Exception as e:
                fix_log.append(f"Failed to fix decorative overlap on slide {issue['slide']}: {e}")

    for issue in issues:
        if issue["type"] == "text_overflow":
            elem_id = issue["element"]
            slide_id = issue["slide_id"]
            container_h = issue.get("container_height_emu", 0)
            if container_h <= 0:
                continue

            slide = slides_by_id.get(slide_id)
            if not slide:
                continue
            elem = None
            for pe in slide.get("pageElements", []):
                if pe["objectId"] == elem_id:
                    elem = pe
                    break
            if not elem:
                continue

            text_elements = elem.get("shape", {}).get("text", {}).get("textElements", [])
            text_runs = [te for te in text_elements if "textRun" in te]
            if not text_runs:
                continue

            full_text = "".join(tr["textRun"]["content"] for tr in text_runs)
            line_count = full_text.count("\n")
            if line_count <= 0:
                continue

            sizes = set()
            for tr in text_runs:
                fs = tr["textRun"].get("style", {}).get("fontSize", {}).get("magnitude")
                if fs:
                    sizes.add(fs)
            if not sizes:
                continue
            current_max = max(sizes)

            target_size = current_max
            for _ in range(5):
                target_size -= 2
                if target_size < 8:
                    break
                est_height = line_count * target_size * 12700 * 1.4
                if est_height <= container_h:
                    break

            if target_size < current_max and target_size >= 8:
                try:
                    batch_update(pres_id, [{
                        "updateTextStyle": {
                            "objectId": elem_id,
                            "textRange": {"type": "ALL"},
                            "style": {"fontSize": {"magnitude": target_size, "unit": "PT"}},
                            "fields": "fontSize"
                        }
                    }])
                    fixes_applied += 1
                    fix_log.append(f"Reduced font from {current_max}pt to {target_size}pt on element {elem_id} (slide {issue['slide']})")
                except Exception as e:
                    fix_log.append(f"Failed to fix text overflow on {elem_id}: {e}")

    _invalidate_presentation_cache(pres_id)

    revalidation = validate_presentation(pres_id)

    return {
        "fixes_applied": fixes_applied,
        "fix_log": fix_log,
        "remaining_errors": revalidation["errors"],
        "remaining_warnings": revalidation["warnings"],
        "status": "PASS" if revalidation["errors"] == 0 else "NEEDS_ATTENTION",
        "remaining_issues": revalidation["issues"]
    }


def export_thumbnails(pres_id: str, output_dir: str) -> Dict:
    """
    Export PNG thumbnails for all slides in a presentation.

    Downloads LARGE-size thumbnails via the Slides API and saves them
    to the specified directory as slide_01.png, slide_02.png, etc.
    """
    import urllib.request

    os.makedirs(output_dir, exist_ok=True)

    pres = get_presentation(pres_id)
    slides = pres.get("slides", [])
    token = get_access_token()
    exported = []
    errors = []

    for i, slide in enumerate(slides):
        page_id = slide["objectId"]
        filename = f"slide_{i + 1:02d}.png"
        filepath = os.path.join(output_dir, filename)

        thumb_url = (
            f"https://slides.googleapis.com/v1/presentations/{pres_id}"
            f"/pages/{page_id}/thumbnail"
            f"?thumbnailProperties.thumbnailSize=LARGE"
            f"&thumbnailProperties.mimeType=PNG"
        )

        try:
            req = urllib.request.Request(thumb_url, headers={
                "Authorization": f"Bearer {token}",
                "x-goog-user-project": "gcp-sandbox-field-eng"
            })
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())
                content_url = data.get("contentUrl")
                if content_url:
                    urllib.request.urlretrieve(content_url, filepath)
                    exported.append({"slide": i + 1, "page_id": page_id, "file": filepath})
                else:
                    errors.append({"slide": i + 1, "error": "No contentUrl in response"})
        except Exception as e:
            errors.append({"slide": i + 1, "error": str(e)})

    return {
        "presentation_id": pres_id,
        "output_dir": output_dir,
        "exported": len(exported),
        "errors": len(errors),
        "files": exported,
        "export_errors": errors
    }


def _set_placeholder_with_fallback(pres_id: str, page_id: str, primary_type: str, fallback_types: List[str], text: str) -> bool:
    """Try to set placeholder text, falling back to alternative placeholder types."""
    for ptype in [primary_type] + fallback_types:
        try:
            set_placeholder_text(pres_id, page_id, ptype, text)
            return True
        except RuntimeError:
            continue
    return False


def _set_indexed_body_placeholders(pres_id: str, page_id: str, texts: List[str]) -> int:
    """Set text on BODY placeholders sorted by spatial position (left-to-right, top-to-bottom).
    
    The placeholder index order does NOT match visual layout order in the Databricks template.
    This function sorts placeholders by their x-position (column) first, then y-position (row)
    to match the expected visual order: col1-header, col1-body, col2-header, col2-body, etc.
    
    Returns the number of placeholders successfully set.
    """
    elements = get_slide_elements(pres_id, page_id)
    body_elements = []
    for elem in elements:
        shape = elem.get("shape", {})
        ph = shape.get("placeholder", {})
        if ph.get("type") == "BODY":
            transform = elem.get("transform", {})
            x = transform.get("translateX", 0)
            y = transform.get("translateY", 0)
            body_elements.append({
                "objectId": elem["objectId"],
                "x": x,
                "y": y
            })
    
    body_elements.sort(key=lambda p: (p["x"], p["y"]))
    
    count = 0
    warnings = []
    for i, text in enumerate(texts):
        if i < len(body_elements):
            try:
                replace_shape_text(pres_id, body_elements[i]["objectId"], text)
                count += 1
            except Exception as exc:
                warnings.append(f"Failed to set BODY placeholder {i} ({body_elements[i]['objectId']}): {exc}")
    if warnings:
        print(f"Warnings setting body placeholders: {'; '.join(warnings)}", file=sys.stderr)
    return count


LAYOUTS_WITH_CENTERED_TITLE = {"title", "title_alt", "closing", "closing_alt", "power_statement"}
LAYOUTS_WITH_SUBTITLE = {"title", "content_subtitle", "quote_dark", "quote_dark_2", "quote_dark_3", "quote_white"}
MULTI_COLUMN_LAYOUTS = {"content_2col", "content_3col", "content_2col_box", "content_3box", "content_4box"}
QUOTE_LAYOUTS = {"quote_dark", "quote_dark_2", "quote_dark_3", "quote_white"}


def _rename_drive_presentation_title(file_id: str, title: str) -> None:
    """Best-effort presentation rename via Drive API."""
    resp = api_call(
        "PATCH",
        f"https://www.googleapis.com/drive/v3/files/{file_id}",
        {"name": title},
    )
    if "error" in resp:
        print(
            "Warning: could not rename presentation %s: %s"
            % (file_id, resp.get("error")),
            file=sys.stderr,
        )


def _prepare_existing_presentation_for_spec(pres_id: str) -> Optional[str]:
    """Remove extra slides from an existing presentation; keep one placeholder page.

    Returns the objectId of the remaining slide (deleted on first new slide add), or
    None if the presentation has no slides.
    """
    slide_ids = get_slide_ids(pres_id)
    if not slide_ids:
        return None
    if len(slide_ids) > 1:
        requests = [{"deleteObject": {"objectId": sid}} for sid in slide_ids[:-1]]
        batch_update(pres_id, requests)
        _invalidate_presentation_cache(pres_id)
    remaining = get_slide_ids(pres_id)
    return remaining[0] if remaining else None


def create_presentation_from_spec(
    title: str,
    slides: List[Dict],
    template_id: str = DATABRICKS_TEMPLATE_ID,
    theme: str = "light",
    file_id: Optional[str] = None,
) -> Dict:
    """
    Create a complete presentation from a specification.

    Args:
        title: Presentation title
        slides: List of slide specs, each containing:
            - layout: Layout name (e.g., "title", "content_basic")
            - title: Optional slide title text
            - subtitle: Optional subtitle text (for title/quote layouts that use SUBTITLE placeholder)
            - body: Optional body text (for single-body layouts like content_basic)
            - columns: Optional list of strings for multi-column layouts (content_2col, content_3col, etc.)
            - table: Optional dict with {rows, cols, data} for adding a table to the slide
                     data is a 2D list of strings. Uses title_only layout recommended.
                     Optional keys: x, y, width, height (inches) for custom positioning.
            - replacements: Optional dict of text replacements {find: replace}
            - bullets: Optional bool, if True apply bullet formatting to body text (default: False)
        template_id: Template to use (ignored when ``file_id`` is set)
        theme: "light" or "dark"
        file_id: If set, rebuild slides inside this existing presentation (same URL).

    Returns:
        Dict with presentationId, url, and slideIds

    Example:
        slides = [
            {"layout": "title", "title": "My Presentation", "subtitle": "A great subtitle"},
            {"layout": "content_basic", "title": "Overview", "body": "Point one\\nPoint two\\nPoint three", "bullets": True},
            {"layout": "content_2col", "title": "Comparison", "columns": ["Left Header", "Left body text", "Right Header", "Right body text"]},
            {"layout": "closing"}
        ]
        result = create_presentation_from_spec("Demo Deck", slides)
    """
    if file_id:
        try:
            _rename_drive_presentation_title(file_id, title)
        except Exception as exc:
            print(
                "Warning: rename failed for presentation %s: %s" % (file_id, exc),
                file=sys.stderr,
            )
        pres_id = file_id
        leftover_slide_id = _prepare_existing_presentation_for_spec(pres_id)
        if leftover_slide_id is None:
            raise RuntimeError(
                "Existing presentation has no slides — cannot rebuild in place"
            )
    else:
        pres_id = create_from_template(title, template_id)

        initial_slides = get_slide_ids(pres_id)
        leftover_slide_id = initial_slides[0] if initial_slides else None

    slide_ids = []
    warnings = []

    for spec in slides:
        layout_name = spec.get("layout", "content_basic")

        result = add_slide_from_template(pres_id, layout_name, theme=theme)

        if "error" in result:
            warnings.append(f"Failed to add slide with layout '{layout_name}': {result['error']}")
            continue

        page_id = result.get("pageId")
        if not page_id:
            continue

        slide_ids.append(page_id)

        if leftover_slide_id:
            delete_slide(pres_id, leftover_slide_id)
            leftover_slide_id = None

        # Quote layouts: 2 BODY placeholders (quote text + attribution), no TITLE
        if layout_name in QUOTE_LAYOUTS:
            quote_texts = []
            if "title" in spec:
                quote_texts.append(spec["title"])
            if "body" in spec:
                quote_texts.append(spec["body"])
            elif "subtitle" in spec:
                quote_texts.append(spec["subtitle"])
            if quote_texts:
                count = _set_indexed_body_placeholders(pres_id, page_id, quote_texts)
                if count == 0:
                    warnings.append(f"Slide '{layout_name}': could not set quote text")
        else:
            # Set title - try CENTERED_TITLE first for title-style layouts, then fall back
            if "title" in spec:
                if layout_name in LAYOUTS_WITH_CENTERED_TITLE:
                    ok = _set_placeholder_with_fallback(pres_id, page_id, "CENTERED_TITLE", ["TITLE"], spec["title"])
                else:
                    ok = _set_placeholder_with_fallback(pres_id, page_id, "TITLE", ["CENTERED_TITLE"], spec["title"])
                if not ok:
                    warnings.append(f"Slide '{layout_name}': could not set title text")

            # Handle content_subtitle layout specially: it has 2 BODY placeholders
            # (subtitle area + body area), no SUBTITLE type placeholder
            if layout_name == "content_subtitle" and ("subtitle" in spec or "body" in spec):
                body_texts = []
                if "subtitle" in spec:
                    body_texts.append(spec["subtitle"])
                if "body" in spec:
                    body_texts.append(spec["body"])
                count = _set_indexed_body_placeholders(pres_id, page_id, body_texts)
                if count == 0:
                    warnings.append(f"Slide '{layout_name}': could not set subtitle/body text")

                if spec.get("bullets") and "body" in spec:
                    try:
                        elements = get_slide_elements(pres_id, page_id)
                        body_elements = []
                        for elem in elements:
                            shape = elem.get("shape", {})
                            ph = shape.get("placeholder", {})
                            if ph.get("type") == "BODY":
                                transform = elem.get("transform", {})
                                x = transform.get("translateX", 0)
                                y = transform.get("translateY", 0)
                                body_elements.append((x, y, elem["objectId"]))
                        body_elements.sort(key=lambda e: (e[0], e[1]))
                        # The last BODY placeholder is the body content area
                        if len(body_elements) >= 2:
                            body_obj_id = body_elements[-1][2]
                            batch_update(pres_id, [{
                                "createParagraphBullets": {
                                    "objectId": body_obj_id,
                                    "textRange": {"type": "ALL"},
                                    "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"
                                }
                            }])
                    except Exception:
                        pass
            else:
                # Set subtitle (for title/quote layouts)
                if "subtitle" in spec:
                    ok = _set_placeholder_with_fallback(pres_id, page_id, "SUBTITLE", ["BODY"], spec["subtitle"])
                    if not ok:
                        warnings.append(f"Slide '{layout_name}': could not set subtitle text")

                # For "body" field on title layout, map to SUBTITLE since there's no BODY placeholder
                if "body" in spec and layout_name in LAYOUTS_WITH_CENTERED_TITLE and "subtitle" not in spec:
                    ok = _set_placeholder_with_fallback(pres_id, page_id, "SUBTITLE", ["BODY"], spec["body"])
                    if not ok:
                        warnings.append(f"Slide '{layout_name}': could not set body/subtitle text")
                elif "body" in spec and layout_name not in LAYOUTS_WITH_CENTERED_TITLE:
                    ok = _set_placeholder_with_fallback(pres_id, page_id, "BODY", [], spec["body"])
                    if not ok:
                        warnings.append(f"Slide '{layout_name}': could not set body text")

                    if spec.get("bullets"):
                        try:
                            body_id = find_placeholder(pres_id, page_id, "BODY")
                            if body_id:
                                batch_update(pres_id, [{
                                    "createParagraphBullets": {
                                        "objectId": body_id,
                                        "textRange": {"type": "ALL"},
                                        "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"
                                    }
                                }])
                        except Exception:
                            pass

        # Set column content for multi-column layouts
        if "columns" in spec and layout_name in MULTI_COLUMN_LAYOUTS:
            count = _set_indexed_body_placeholders(pres_id, page_id, spec["columns"])
            if count == 0:
                warnings.append(f"Slide '{layout_name}': could not set any column text")

        # Add table if specified
        if "table" in spec:
            tbl = spec["table"]
            tbl_rows = tbl.get("rows", len(tbl.get("data", [])))
            tbl_cols = tbl.get("cols", len(tbl["data"][0]) if tbl.get("data") else 3)
            tbl_x = tbl.get("x", 0.5)
            tbl_y = tbl.get("y", 1.5)
            tbl_width = tbl.get("width", 12.0)
            tbl_height = tbl.get("height", 4.5)
            try:
                # Clear BODY placeholder if present to avoid overlap
                body_ph = find_placeholder(pres_id, page_id, "BODY")
                if body_ph:
                    batch_update(pres_id, [{"deleteText": {"objectId": body_ph, "textRange": {"type": "ALL"}}}])
            except Exception:
                pass
            try:
                tbl_result = create_table(pres_id, page_id, tbl_rows, tbl_cols, tbl_x, tbl_y, tbl_width, tbl_height)
                if "tableId" in tbl_result and tbl.get("data"):
                    fill_table(pres_id, tbl_result["tableId"], tbl["data"])
                    style_table_header(pres_id, tbl_result["tableId"], tbl_cols)
                    is_dark_layout = layout_name in (
                        "content_basic_dark", "title_dark", "headline_04",
                        "section_break_1", "section_break_2", "section_break_3",
                        "section_break_4", "section_break_5", "section_break_6",
                        "quote_dark", "quote_dark_2", "quote_dark_3",
                        "power_statement", "closing", "closing_alt", "title", "title_alt",
                    )
                    if is_dark_layout:
                        style_table_body_text(pres_id, tbl_result["tableId"], tbl_rows, tbl_cols)
                    else:
                        style_table_body_text(
                            pres_id, tbl_result["tableId"], tbl_rows, tbl_cols,
                            text_color=DATABRICKS_COLORS["dark_teal"]
                        )
            except Exception as e:
                warnings.append(f"Slide '{layout_name}': table creation failed: {e}")

        # Apply text replacements
        if "replacements" in spec:
            for find, replace in spec["replacements"].items():
                replace_all_text(pres_id, find, replace, page_ids=[page_id])

    result = {
        "presentationId": pres_id,
        "url": f"https://docs.google.com/presentation/d/{pres_id}/edit",
        "slideIds": slide_ids
    }
    if warnings:
        result["warnings"] = warnings
    return result


# =============================================================================
# MAIN CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Build and manage Google Slides presentations",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Create presentation
    create_parser = subparsers.add_parser("create", help="Create a new presentation")
    create_parser.add_argument("--title", required=True, help="Presentation title")

    # Get presentation info
    info_parser = subparsers.add_parser("info", help="Get presentation info")
    info_parser.add_argument("--pres-id", required=True, help="Presentation ID")
    info_parser.add_argument("--full", action="store_true", help="Show full JSON")

    # List slides
    list_parser = subparsers.add_parser("list-slides", help="List all slides")
    list_parser.add_argument("--pres-id", required=True, help="Presentation ID")

    # Add slide
    slide_parser = subparsers.add_parser("add-slide", help="Add a new slide")
    slide_parser.add_argument("--pres-id", required=True, help="Presentation ID")
    slide_parser.add_argument("--layout", default="BLANK", help="Layout type")
    slide_parser.add_argument("--index", type=int, help="Insertion index")

    # Duplicate slide
    dup_parser = subparsers.add_parser("duplicate-slide", help="Duplicate a slide")
    dup_parser.add_argument("--pres-id", required=True, help="Presentation ID")
    dup_parser.add_argument("--page-id", required=True, help="Slide ID to duplicate")

    # Delete slide
    del_parser = subparsers.add_parser("delete-slide", help="Delete a slide")
    del_parser.add_argument("--pres-id", required=True, help="Presentation ID")
    del_parser.add_argument("--page-id", required=True, help="Slide ID to delete")

    # Set background
    bg_parser = subparsers.add_parser("set-background", help="Set slide background")
    bg_parser.add_argument("--pres-id", required=True, help="Presentation ID")
    bg_parser.add_argument("--page-id", required=True, help="Slide ID")
    bg_parser.add_argument("--color", help="RGB color as JSON")
    bg_parser.add_argument("--image-url", help="Background image URL")

    # Add text box
    text_parser = subparsers.add_parser("add-text-box", help="Add a text box")
    text_parser.add_argument("--pres-id", required=True, help="Presentation ID")
    text_parser.add_argument("--page-id", required=True, help="Slide ID")
    text_parser.add_argument("--text", required=True, help="Text content (use \\n for newlines, \\t for tabs)")
    text_parser.add_argument("--x", type=float, default=1, help="X position (inches)")
    text_parser.add_argument("--y", type=float, default=1, help="Y position (inches)")
    text_parser.add_argument("--width", type=float, default=3, help="Width (inches)")
    text_parser.add_argument("--height", type=float, default=1, help="Height (inches)")
    text_parser.add_argument("--font-size", type=float, default=18, help="Font size (pt)")
    text_parser.add_argument("--bold", action="store_true", help="Bold text")

    # Add image
    img_parser = subparsers.add_parser("add-image", help="Add an image")
    img_parser.add_argument("--pres-id", required=True, help="Presentation ID")
    img_parser.add_argument("--page-id", required=True, help="Slide ID")
    img_parser.add_argument("--url", required=True, help="Image URL")
    img_parser.add_argument("--x", type=float, default=1, help="X position (inches)")
    img_parser.add_argument("--y", type=float, default=1, help="Y position (inches)")
    img_parser.add_argument("--width", type=float, default=3, help="Width (inches)")
    img_parser.add_argument("--height", type=float, default=2, help="Height (inches)")

    # Add table
    table_parser = subparsers.add_parser("add-table", help="Add a table")
    table_parser.add_argument("--pres-id", required=True, help="Presentation ID")
    table_parser.add_argument("--page-id", required=True, help="Slide ID")
    table_parser.add_argument("--rows", type=int, required=True, help="Number of rows")
    table_parser.add_argument("--cols", type=int, required=True, help="Number of columns")
    table_parser.add_argument("--data", required=True, help="JSON 2D array of cell values")
    table_parser.add_argument("--position", help="Predefined position name (e.g., 'table_full', 'table_full_dark')")
    table_parser.add_argument("--x", type=float, help="X position (inches) - overrides position")
    table_parser.add_argument("--y", type=float, help="Y position (inches) - overrides position")
    table_parser.add_argument("--width", type=float, help="Width (inches) - overrides position")
    table_parser.add_argument("--height", type=float, help="Height (inches) - overrides position")
    table_parser.add_argument("--dark", action="store_true", help="Use dark styling (white text, orange header, dark positions)")

    # Add chart from Sheets
    chart_parser = subparsers.add_parser("add-chart", help="Add a chart from Sheets")
    chart_parser.add_argument("--pres-id", required=True, help="Presentation ID")
    chart_parser.add_argument("--page-id", required=True, help="Slide ID")
    chart_parser.add_argument("--spreadsheet-id", required=True, help="Google Sheets ID")
    chart_parser.add_argument("--chart-id", type=int, required=True, help="Chart ID in sheet")
    chart_parser.add_argument("--x", type=float, default=0.5, help="X position (inches)")
    chart_parser.add_argument("--y", type=float, default=1.5, help="Y position (inches)")
    chart_parser.add_argument("--width", type=float, default=5, help="Width (inches)")
    chart_parser.add_argument("--height", type=float, default=3, help="Height (inches)")
    chart_parser.add_argument("--not-linked", action="store_true", help="Don't link to sheet")

    # Copy presentation
    copy_parser = subparsers.add_parser("copy", help="Copy entire presentation")
    copy_parser.add_argument("--pres-id", required=True, help="Source presentation ID")
    copy_parser.add_argument("--title", required=True, help="New presentation title")

    # Set placeholder text
    placeholder_parser = subparsers.add_parser("set-placeholder", help="Set placeholder text")
    placeholder_parser.add_argument("--pres-id", required=True, help="Presentation ID")
    placeholder_parser.add_argument("--page-id", required=True, help="Slide ID")
    placeholder_parser.add_argument("--type", required=True, help="TITLE, SUBTITLE, BODY")
    placeholder_parser.add_argument("--text", required=True, help="Text content (use \\n for newlines, \\t for tabs)")

    # Create from Databricks template
    template_parser = subparsers.add_parser("create-from-template", help="Create presentation from Databricks template")
    template_parser.add_argument("--title", required=True, help="Presentation title")
    template_parser.add_argument("--template-id", default=DATABRICKS_TEMPLATE_ID, help="Template ID (default: Databricks Corporate)")
    template_parser.add_argument("--keep-samples", action="store_true", help="Keep sample slides from template")

    # Add slide from template layout
    tslide_parser = subparsers.add_parser("add-template-slide", help="Add slide using Databricks template layout")
    tslide_parser.add_argument("--pres-id", required=True, help="Presentation ID")
    tslide_parser.add_argument("--layout", required=True, help="Layout name: shorthand (title, content_basic, section_break_1, closing) or full display name (Title and Content, Headline 01)")
    tslide_parser.add_argument("--theme", default="light", choices=["light", "dark"], help="Theme for layout selection")
    tslide_parser.add_argument("--index", type=int, help="Insertion index")

    # List available layouts
    layouts_parser = subparsers.add_parser("list-layouts", help="List available layouts in presentation")
    layouts_parser.add_argument("--pres-id", required=True, help="Presentation ID")

    # List template layouts (without needing a presentation)
    tlayouts_parser = subparsers.add_parser("list-template-layouts", help="List available Databricks template layouts")
    tlayouts_parser.add_argument("--theme", default="light", choices=["light", "dark"], help="Theme (light or dark)")

    # Replace text across presentation
    replace_parser = subparsers.add_parser("replace-text", help="Replace text across presentation")
    replace_parser.add_argument("--pres-id", required=True, help="Presentation ID")
    replace_parser.add_argument("--find", required=True, help="Text to find")
    replace_parser.add_argument("--replace", required=True, help="Replacement text")
    replace_parser.add_argument("--match-case", action="store_true", help="Match case")

    # List placeholders on a slide
    placeholders_parser = subparsers.add_parser("list-placeholders", help="List placeholders on a slide")
    placeholders_parser.add_argument("--pres-id", required=True, help="Presentation ID")
    placeholders_parser.add_argument("--page-id", required=True, help="Slide ID")

    # List predefined positions
    subparsers.add_parser("list-positions", help="List predefined positions for spatial layout")

    # Validate presentation
    validate_parser = subparsers.add_parser("validate", help="Validate presentation for common issues")
    validate_parser.add_argument("--pres-id", required=True, help="Presentation ID")

    # Auto-fix presentation issues
    autofix_parser = subparsers.add_parser("auto-fix", help="Automatically fix common validation issues")
    autofix_parser.add_argument("--pres-id", required=True, help="Presentation ID")

    # Export thumbnails
    thumb_parser = subparsers.add_parser("export-thumbnails", help="Export PNG thumbnails for all slides")
    thumb_parser.add_argument("--pres-id", required=True, help="Presentation ID")
    thumb_parser.add_argument("--output-dir", default="/tmp/slides", help="Output directory for PNGs")

    # Create from spec (JSON)
    spec_parser = subparsers.add_parser("create-from-spec", help="Create presentation from JSON spec")
    spec_parser.add_argument("--title", required=True, help="Presentation title")
    spec_parser.add_argument("--spec", required=True, help="JSON array of slide specs")
    spec_parser.add_argument("--theme", default="light", choices=["light", "dark"], help="Theme")

    args = parser.parse_args()

    def _decode_escapes(s: str) -> str:
        """Decode common escape sequences (\\n, \\t, \\', \\") in CLI text arguments."""
        if s is None:
            return s
        return s.replace("\\n", "\n").replace("\\t", "\t").replace("\\'", "'").replace('\\"', '"')

    for attr in ("text", "find", "replace"):
        if hasattr(args, attr) and isinstance(getattr(args, attr), str):
            setattr(args, attr, _decode_escapes(getattr(args, attr)))

    try:
        if args.command == "create":
            pres_id = create_presentation(args.title)
            print(json.dumps({
                "presentationId": pres_id,
                "url": f"https://docs.google.com/presentation/d/{pres_id}/edit"
            }, indent=2))

        elif args.command == "info":
            pres = get_presentation(args.pres_id)
            if args.full:
                print(json.dumps(pres, indent=2))
            else:
                print(json.dumps({
                    "presentationId": pres["presentationId"],
                    "title": pres.get("title", ""),
                    "slideCount": len(pres.get("slides", [])),
                    "slideIds": [s["objectId"] for s in pres.get("slides", [])]
                }, indent=2))

        elif args.command == "list-slides":
            pres = get_presentation(args.pres_id)
            slides = []
            for i, slide in enumerate(pres.get("slides", [])):
                slides.append({
                    "index": i,
                    "objectId": slide["objectId"],
                    "elementCount": len(slide.get("pageElements", []))
                })
            print(json.dumps({"slides": slides}, indent=2))

        elif args.command == "add-slide":
            result = add_slide(args.pres_id, args.layout, args.index)
            print(json.dumps(result, indent=2))

        elif args.command == "duplicate-slide":
            result = duplicate_slide(args.pres_id, args.page_id)
            print(json.dumps(result, indent=2))

        elif args.command == "delete-slide":
            result = delete_slide(args.pres_id, args.page_id)
            print(json.dumps(result, indent=2))

        elif args.command == "set-background":
            color = json.loads(args.color) if args.color else None
            result = set_slide_background(args.pres_id, args.page_id, color, args.image_url)
            print(json.dumps(result, indent=2))

        elif args.command == "add-text-box":
            result = create_text_box(
                args.pres_id, args.page_id, args.text,
                args.x, args.y, args.width, args.height,
                args.font_size, args.bold
            )
            print(json.dumps(result, indent=2))

        elif args.command == "add-image":
            result = create_image(
                args.pres_id, args.page_id, args.url,
                args.x, args.y, args.width, args.height
            )
            print(json.dumps(result, indent=2))

        elif args.command == "add-table":
            data = json.loads(args.data)

            # Determine if using dark mode positioning
            use_dark = args.dark

            # Get position from name or use explicit coordinates
            if args.position:
                x, y, width, height = get_position(args.position)
            elif use_dark:
                # Default to dark table position
                x, y, width, height = get_position("table_full_dark")
            else:
                # Use explicit values or defaults
                x = args.x if args.x is not None else 0.5
                y = args.y if args.y is not None else BODY_TOP
                width = args.width if args.width is not None else 9.0
                height = args.height if args.height is not None else 3.0

            # Allow explicit coords to override position
            if args.x is not None:
                x = args.x
            if args.y is not None:
                y = args.y
            if args.width is not None:
                width = args.width
            if args.height is not None:
                height = args.height

            # Create table
            result = create_table(
                args.pres_id, args.page_id, args.rows, args.cols,
                x, y, width, height
            )
            if "error" not in result and "tableId" in result:
                # Fill table
                fill_result = fill_table(args.pres_id, result["tableId"], data)

                # Style based on dark mode
                if use_dark:
                    # Dark mode: orange header with white text, white body text
                    style_result = style_table_for_dark_background(
                        args.pres_id, result["tableId"], args.rows, args.cols
                    )
                else:
                    # Light mode: navy header with white text (default)
                    style_result = style_table_header(args.pres_id, result["tableId"], args.cols)

                result["filled"] = "error" not in fill_result
                result["styled"] = "error" not in style_result
                result["dark_mode"] = use_dark
                result["position"] = {"x": x, "y": y, "width": width, "height": height}
            print(json.dumps(result, indent=2))

        elif args.command == "add-chart":
            result = create_sheets_chart(
                args.pres_id, args.page_id, args.spreadsheet_id, args.chart_id,
                args.x, args.y, args.width, args.height,
                linked=not args.not_linked
            )
            print(json.dumps(result, indent=2))

        elif args.command == "copy":
            new_id = copy_presentation(args.pres_id, args.title)
            print(json.dumps({
                "presentationId": new_id,
                "url": f"https://docs.google.com/presentation/d/{new_id}/edit"
            }, indent=2))

        elif args.command == "set-placeholder":
            result = set_placeholder_text(args.pres_id, args.page_id, args.type, args.text)
            print(json.dumps(result, indent=2))

        elif args.command == "create-from-template":
            pres_id = create_from_template(
                args.title,
                args.template_id,
                delete_sample_slides=not args.keep_samples
            )
            print(json.dumps({
                "presentationId": pres_id,
                "url": f"https://docs.google.com/presentation/d/{pres_id}/edit",
                "template": "Databricks Corporate PPT Template"
            }, indent=2))

        elif args.command == "add-template-slide":
            # Use name-based lookup for dynamic layout resolution
            # This works correctly after copying a template (when IDs change)
            result = add_template_slide_by_name(
                args.pres_id,
                args.layout,
                theme=args.theme,
                insertion_index=args.index
            )
            print(json.dumps(result, indent=2))

        elif args.command == "list-layouts":
            layouts = list_layouts(args.pres_id)
            print(json.dumps({"layouts": layouts}, indent=2))

        elif args.command == "list-template-layouts":
            layouts = DATABRICKS_LAYOUTS_DARK if args.theme == "dark" else DATABRICKS_LAYOUTS_LIGHT
            print("Available Databricks template layouts ({} theme):".format(args.theme))
            print()
            categories = {
                "Title slides": ["title", "title_alt"],
                "Content (white bg)": ["content_basic", "content_subtitle", "content_2col",
                           "content_3col", "content_2col_box", "content_3box",
                           "content_4box", "title_only"],
                "Content (dark bg)": ["content_basic_dark", "title_dark", "headline_04"],
                "Section breaks": [f"section_break_{i}" for i in range(1, 7)],
                "Quotes": ["quote_dark", "quote_dark_2", "quote_dark_3", "quote_white"],
                "Special": ["blank", "power_statement", "closing", "closing_alt"],
            }
            for category, names in categories.items():
                available = [n for n in names if n in layouts]
                if available:
                    print(f"  {category}:")
                    for name in available:
                        print(f"    - {name}")
            print()

        elif args.command == "replace-text":
            result = replace_all_text(args.pres_id, args.find, args.replace, args.match_case)
            print(json.dumps(result, indent=2))

        elif args.command == "list-placeholders":
            placeholders = get_all_placeholders(args.pres_id, args.page_id)
            print(json.dumps({"placeholders": placeholders}, indent=2))

        elif args.command == "list-positions":
            print("Predefined positions for spatial layout:")
            print(f"\nSlide dimensions: {SLIDE_WIDTH}\" x {SLIDE_HEIGHT}\" (16:9)")
            print(f"Content area: {CONTENT_WIDTH}\" x {CONTENT_HEIGHT}\" (with {MARGIN_LEFT}\" margins)")
            print(f"Body area (light slides): starts at y={BODY_TOP}\", height={BODY_HEIGHT}\"")
            print(f"Body area (dark slides):  starts at y={DARK_BODY_TOP}\", height={DARK_BODY_HEIGHT:.2f}\"")
            print("\nAvailable positions (x, y, width, height in inches):")
            categories = {
                "Full area": ["full", "full_no_title"],
                "Horizontal thirds": ["left_third", "center_third", "right_third"],
                "Horizontal halves": ["left_half", "right_half"],
                "Vertical halves": ["top_half", "bottom_half"],
                "Quadrants": ["top_left", "top_right", "bottom_left", "bottom_right"],
                "Centered": ["center_large", "center_medium", "center_small"],
                "Tables (light)": ["table_full", "table_left", "table_right"],
                "Tables (dark)": ["table_full_dark", "table_left_dark", "table_right_dark"],
                "Charts (light)": ["chart_full", "chart_left", "chart_right"],
                "Charts (dark)": ["chart_full_dark", "chart_left_dark", "chart_right_dark"],
                "Images": ["image_left", "image_right", "image_center", "image_background"],
                "Text boxes": ["text_title_area", "text_subtitle", "text_footer", "text_caption"],
            }
            for category, names in categories.items():
                print(f"\n  {category}:")
                for name in names:
                    if name in POSITIONS:
                        x, y, w, h = POSITIONS[name]
                        print(f"    {name}: ({x:.2f}, {y:.2f}, {w:.2f}, {h:.2f})")

        elif args.command == "validate":
            result = validate_presentation(args.pres_id)
            print(json.dumps(result, indent=2))

        elif args.command == "auto-fix":
            result = auto_fix_presentation(args.pres_id)
            print(json.dumps(result, indent=2))

        elif args.command == "export-thumbnails":
            result = export_thumbnails(args.pres_id, args.output_dir)
            print(json.dumps(result, indent=2))

        elif args.command == "create-from-spec":
            slides = json.loads(args.spec)
            result = create_presentation_from_spec(args.title, slides, theme=args.theme)
            print(json.dumps(result, indent=2))

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
