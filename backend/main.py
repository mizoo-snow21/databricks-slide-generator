from __future__ import annotations

import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from routers.decks import router as decks_router, warm_pptx_template_cache
from routers.genie import router as genie_router
from routers.templates import router as templates_router

app = FastAPI(title="Genie Slide", version="0.1.0")


@app.on_event("startup")
def _warm_caches() -> None:
    # Run in background so app accepts requests immediately.
    threading.Thread(target=warm_pptx_template_cache, daemon=True).start()


app.include_router(templates_router)
app.include_router(decks_router)
app.include_router(genie_router)

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
        # Serve real files in dist root (e.g., /databricks-logo-*.svg, /favicon.ico)
        # before falling back to the SPA index.
        candidate = FRONTEND_DIST / full_path
        if candidate.is_file() and candidate.resolve().is_relative_to(
            FRONTEND_DIST.resolve()
        ):
            return FileResponse(candidate)
        return FileResponse(index_file)
