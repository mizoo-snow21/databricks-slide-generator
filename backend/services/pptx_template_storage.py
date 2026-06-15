from __future__ import annotations

import shutil
import time
from pathlib import Path

STORAGE_ROOT = Path(__file__).parent.parent / "data" / "pptx-templates"
TEMP_ROOT = Path(__file__).parent.parent / "data" / "pptx-templates-tmp"


def save_pptx_temp(upload_id: str, pptx_bytes: bytes) -> Path:
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    target = TEMP_ROOT / f"{upload_id}.pptx"
    target.write_bytes(pptx_bytes)
    return target


def get_pptx_temp_path(upload_id: str) -> Path | None:
    p = TEMP_ROOT / f"{upload_id}.pptx"
    return p if p.is_file() else None


def finalize_pptx_for_template(upload_id: str, template_id: str) -> str | None:
    temp = get_pptx_temp_path(upload_id)
    if temp is None:
        return None
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    dest = STORAGE_ROOT / f"{template_id}.pptx"
    shutil.move(str(temp), str(dest))
    return str(dest.resolve())


def cleanup_old_temp_files(max_age_seconds: int = 3600) -> None:
    if not TEMP_ROOT.is_dir():
        return
    cutoff = time.time() - max_age_seconds
    for path in TEMP_ROOT.glob("*.pptx"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
        except OSError:
            pass


def save_pptx_for_template(template_id: str, pptx_bytes: bytes) -> str:
    """Save uploaded PPTX bytes to disk, return absolute path string."""
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    target = STORAGE_ROOT / f"{template_id}.pptx"
    target.write_bytes(pptx_bytes)
    return str(target.resolve())


def get_pptx_path_for_template(template_id: str) -> Path | None:
    """Return Path if file exists, else None."""
    p = STORAGE_ROOT / f"{template_id}.pptx"
    return p if p.is_file() else None
