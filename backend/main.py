from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Genie Slide", version="0.1.0")

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
ASSETS_DIR = FRONTEND_DIST / "assets"


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if ASSETS_DIR.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=ASSETS_DIR),
        name="assets",
    )

if FRONTEND_DIST.is_dir() and (FRONTEND_DIST / "index.html").is_file():
    index_file = FRONTEND_DIST / "index.html"

    @app.get("/")
    async def spa_root() -> FileResponse:
        return FileResponse(index_file)

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str) -> FileResponse:
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        return FileResponse(index_file)
