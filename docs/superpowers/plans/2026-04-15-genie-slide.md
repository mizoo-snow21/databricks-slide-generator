# Genie Slide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Databricks App that generates Google Slides presentations from Lakeview Dashboards using LLM-driven layout selection and Playwright widget capture.

**Architecture:** React frontend (template/dashboard selection + prompt) → FastAPI backend → Dashboard API for widget data → Playwright for chart screenshots → Foundation Model API for slide composition → gslides_builder.py for Google Slides output.

**Tech Stack:** React, TypeScript, Python, FastAPI, Playwright, Databricks SDK, Foundation Model API, Google Slides API (via gslides_builder.py), Unity Catalog, uv (Python package management)

**Spec:** `docs/superpowers/specs/2026-04-15-genie-slide-design.md`

---

## File Structure

```
genie-slide/
├── app.yaml                          # Databricks App config
├── backend/
│   ├── main.py                       # FastAPI entry point
│   ├── config.py                     # Environment config
│   ├── models.py                     # Pydantic models
│   ├── routers/
│   │   ├── templates.py              # Template CRUD endpoints
│   │   ├── dashboards.py             # Dashboard listing endpoints
│   │   └── generation.py             # Slide generation endpoint
│   ├── services/
│   │   ├── template_service.py       # Template storage (UC tables)
│   │   ├── dashboard_service.py      # Lakeview Dashboard API client
│   │   ├── capture_service.py        # Playwright widget screenshot
│   │   ├── llm_service.py            # Foundation Model API composition
│   │   ├── slides_service.py         # gslides_builder.py wrapper
│   │   └── google_auth_service.py    # Google OAuth flow
│   └── pyproject.toml              # uv managed dependencies
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── index.html
│   └── src/
│       ├── main.tsx                  # React entry
│       ├── App.tsx                   # Router
│       ├── types.ts                  # Shared types
│       ├── api.ts                    # Backend API client
│       ├── pages/
│       │   ├── HomePage.tsx          # Template selection
│       │   ├── DashboardSelectPage.tsx
│       │   ├── GeneratePage.tsx      # Settings + progress + result
│       │   └── AdminTemplatePage.tsx  # Template registration
│       └── components/
│           ├── TemplateCard.tsx
│           ├── DashboardList.tsx
│           └── ProgressIndicator.tsx
└── tests/
    ├── test_models.py
    ├── test_template_service.py
    ├── test_dashboard_service.py
    ├── test_llm_service.py
    ├── test_slides_service.py
    ├── test_capture_service.py
    └── test_generation_router.py
```

---

## Task 1: Project Scaffolding

**Files:**
- Create: `app.yaml`
- Create: `backend/main.py`
- Create: `backend/config.py`
- Create: `backend/pyproject.toml`
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`

- [ ] **Step 1: Create app.yaml**

```yaml
# app.yaml
command:
  - /bin/bash
  - -c
  - |
    cd backend && uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

Note: All dependencies (Python via `uv sync`, npm via `npm install && npm run build`, Playwright via `uv run playwright install --with-deps chromium`) are installed at **build time** before deployment, not at runtime. The `app.yaml` command only starts the server. FastAPI serves the pre-built frontend from `../frontend/dist` via `StaticFiles` mount and a catch-all route (see `backend/main.py` below).

**Build script (`scripts/build.sh`, run before `databricks apps deploy`):**
```bash
#!/bin/bash
set -e
cd frontend && npm install && npm run build
cd ../backend && uv sync && uv run playwright install --with-deps chromium
``` The single `uvicorn` process serves both the API and the React SPA.

- [ ] **Step 2: Create backend/pyproject.toml**

```toml
[project]
name = "genie-slide-backend"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn>=0.30.0",
    "databricks-sdk>=0.30.0",
    "pydantic>=2.9.0",
    "playwright>=1.47.0",
    "httpx>=0.27.0",
]

[tool.uv]
dev-dependencies = [
    "pytest>=8.0.0",
]
```

Then run: `cd backend && uv sync`

- [ ] **Step 3: Create backend/config.py**

```python
# backend/config.py
import os

DATABRICKS_HOST = os.environ.get("DATABRICKS_HOST", "")
DATABRICKS_TOKEN = os.environ.get("DATABRICKS_TOKEN", "")
UC_CATALOG = os.environ.get("UC_CATALOG", "genie_slide")
UC_SCHEMA = os.environ.get("UC_SCHEMA", "app")
GSLIDES_BUILDER_PATH = os.environ.get(
    "GSLIDES_BUILDER_PATH",
    os.path.join(os.path.dirname(__file__), "vendor", "gslides_builder.py"),
)
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
```

- [ ] **Step 4: Create backend/main.py**

```python
# backend/main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

app = FastAPI(title="Genie Slide")


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Serve frontend build
frontend_build = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(frontend_build):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_build, "assets")), name="assets")

    @app.get("/{path:path}")
    def serve_frontend(path: str):
        file_path = os.path.join(frontend_build, path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_build, "index.html"))
```

- [ ] **Step 5: Create frontend scaffolding**

`frontend/package.json`:
```json
{
  "name": "genie-slide-frontend",
  "private": true,
  "version": "0.1.0",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.5.0",
    "vite": "^5.4.0"
  }
}
```

`frontend/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true
  },
  "include": ["src"]
}
```

`frontend/vite.config.ts`:
```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
```

`frontend/index.html`:
```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Genie Slide</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`frontend/src/main.tsx`:
```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
```

`frontend/src/App.tsx`:
```tsx
import { Routes, Route } from "react-router-dom";

function Placeholder({ name }: { name: string }) {
  return <div style={{ padding: 32 }}><h1>{name}</h1><p>Coming soon</p></div>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Placeholder name="Genie Slide" />} />
    </Routes>
  );
}
```

- [ ] **Step 6: Verify backend starts**

Run: `cd backend && uv sync && uv run python -c "from main import app; print('OK')"`
Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add app.yaml backend/ frontend/
git commit -m "feat: project scaffolding with FastAPI + React + Vite"
```

---

## Task 2: Pydantic Models

**Files:**
- Create: `backend/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_models.py
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from models import (
    TemplateBrand,
    TemplateGuidelines,
    Template,
    TemplateCreate,
    DashboardInfo,
    WidgetInfo,
    GenerationRequest,
    GenerationResult,
    GenerationHistoryRecord,
)


def test_template_brand_defaults():
    brand = TemplateBrand(primary="#1A73E8")
    assert brand.primary == "#1A73E8"
    assert brand.font == "Noto Sans JP"


def test_template_guidelines_defaults():
    g = TemplateGuidelines()
    assert g.total_slides_min == 6
    assert g.total_slides_max == 12
    assert "title" in g.must_include
    assert "closing" in g.must_include


def test_template_create():
    t = TemplateCreate(
        name="QBR",
        description="Quarterly review",
        google_slides_template_id="abc123",
    )
    assert t.name == "QBR"
    assert t.theme == "light"


def test_widget_info():
    w = WidgetInfo(
        widget_id="w1",
        title="Revenue",
        viz_type="bar_chart",
        columns=["month", "revenue"],
        row_count=12,
    )
    assert w.query_result_summary is None


def test_generation_request():
    req = GenerationRequest(
        template_id="tpl1",
        dashboard_id="dash1",
    )
    assert req.user_prompt is None


def test_generation_result():
    res = GenerationResult(
        google_slides_url="https://docs.google.com/presentation/d/xxx/edit",
        slide_count=8,
        warnings=[],
    )
    assert res.slide_count == 8
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/yukihiro.mizoguchi/genie-slide && python -m pytest tests/test_models.py -v`
Expected: FAIL (models module not found)

- [ ] **Step 3: Implement models**

```python
# backend/models.py
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


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
    preferred_layouts: List[str] = Field(
        default_factory=lambda: ["title", "content_basic", "content_2col", "title_only", "closing"]
    )
    style_notes: str = "Concise. One message per slide."
    must_include: List[str] = Field(default_factory=lambda: ["title", "closing"])
    chart_preference: str = "Use title_only with table for data-heavy slides"


class TemplateCreate(BaseModel):
    name: str
    description: str = ""
    google_slides_template_id: str
    theme: str = "light"
    brand: TemplateBrand = Field(default_factory=TemplateBrand)
    guidelines: TemplateGuidelines = Field(default_factory=TemplateGuidelines)


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
    columns: List[str] = Field(default_factory=list)
    row_count: int = 0
    query_result_summary: Optional[str] = None
    capture_status: str = "pending"  # pending, captured, capture_failed, unsupported


class GenerationRequest(BaseModel):
    template_id: str
    dashboard_id: str
    user_prompt: Optional[str] = None


class GenerationResult(BaseModel):
    google_slides_url: str
    slide_count: int
    warnings: List[str] = Field(default_factory=list)
    skipped_widgets: List[str] = Field(default_factory=list)


class GenerationHistoryRecord(BaseModel):
    id: str
    template_id: str
    dashboard_id: str
    user_id: str
    user_prompt: Optional[str] = None
    google_slides_url: str
    slide_count: int
    created_at: datetime
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_models.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/models.py tests/test_models.py
git commit -m "feat: add Pydantic models for templates, widgets, generation"
```

---

## Task 3: Template Service

**Files:**
- Create: `backend/services/template_service.py`
- Create: `tests/test_template_service.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_template_service.py
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from services.template_service import TemplateService
from models import TemplateCreate


class TestTemplateServiceInMemory:
    """Test with in-memory store (no Databricks dependency)."""

    def setup_method(self):
        self.svc = TemplateService(use_memory=True)

    def test_create_and_get(self):
        tpl = TemplateCreate(
            name="Test QBR",
            description="Test template",
            google_slides_template_id="gslide_123",
        )
        created = self.svc.create(tpl, user_id="user1")
        assert created.id is not None
        assert created.name == "Test QBR"
        assert created.created_by == "user1"

        fetched = self.svc.get(created.id)
        assert fetched is not None
        assert fetched.name == "Test QBR"

    def test_list_templates(self):
        self.svc.create(
            TemplateCreate(name="A", google_slides_template_id="a"),
            user_id="u1",
        )
        self.svc.create(
            TemplateCreate(name="B", google_slides_template_id="b"),
            user_id="u1",
        )
        templates = self.svc.list_all()
        assert len(templates) == 2

    def test_delete(self):
        created = self.svc.create(
            TemplateCreate(name="Del", google_slides_template_id="d"),
            user_id="u1",
        )
        self.svc.delete(created.id)
        assert self.svc.get(created.id) is None

    def test_get_nonexistent_returns_none(self):
        assert self.svc.get("nonexistent") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_template_service.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement template service**

```python
# backend/services/__init__.py
```

```python
# backend/services/template_service.py
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from models import Template, TemplateCreate


class TemplateService:
    def __init__(self, use_memory: bool = False, sql_client=None):
        self._use_memory = use_memory
        self._sql_client = sql_client
        self._store: Dict[str, Template] = {}

    def create(self, data: TemplateCreate, user_id: str) -> Template:
        template = Template(
            id=str(uuid.uuid4()),
            created_by=user_id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            **data.model_dump(),
        )
        if self._use_memory:
            self._store[template.id] = template
        else:
            self._insert_to_uc(template)
        return template

    def get(self, template_id: str) -> Optional[Template]:
        if self._use_memory:
            return self._store.get(template_id)
        return self._fetch_from_uc(template_id)

    def list_all(self) -> List[Template]:
        if self._use_memory:
            return list(self._store.values())
        return self._list_from_uc()

    def delete(self, template_id: str) -> None:
        if self._use_memory:
            self._store.pop(template_id, None)
        else:
            self._delete_from_uc(template_id)

    # --- Unity Catalog implementations (Phase 1: SQL via Databricks SDK) ---

    @staticmethod
    def _sanitize(value: str) -> str:
        """Escape single quotes to prevent SQL injection."""
        return value.replace("'", "''")

    def _insert_to_uc(self, template: Template) -> None:
        if not self._sql_client:
            raise RuntimeError("SQL client required for UC storage")
        from config import UC_CATALOG, UC_SCHEMA

        table = f"{UC_CATALOG}.{UC_SCHEMA}.slide_templates"
        brand_json = template.brand.model_dump_json()
        guidelines_json = template.guidelines.model_dump_json()
        s = self._sanitize
        self._sql_client.execute(
            f"INSERT INTO {table}"
            " (id, name, description, thumbnail_url, google_slides_template_id,"
            "  theme, brand, guidelines, created_by, created_at, updated_at)"
            " VALUES"
            f" ('{s(template.id)}', '{s(template.name)}', '{s(template.description)}',"
            f"  '{s(template.thumbnail_url or '')}', '{s(template.google_slides_template_id)}',"
            f"  '{s(template.theme)}', '{s(brand_json)}', '{s(guidelines_json)}',"
            f"  '{s(template.created_by)}',"
            f"  '{template.created_at.isoformat()}', '{template.updated_at.isoformat()}')"
        )

    def _fetch_from_uc(self, template_id: str) -> Optional[Template]:
        if not self._sql_client:
            raise RuntimeError("SQL client required for UC storage")
        from config import UC_CATALOG, UC_SCHEMA
        import json

        table = f"{UC_CATALOG}.{UC_SCHEMA}.slide_templates"
        # template_id is a UUID generated internally, but sanitize defensively
        safe_id = self._sanitize(template_id)
        rows = self._sql_client.execute(
            f"SELECT * FROM {table} WHERE id = '{safe_id}'"
        )
        if not rows:
            return None
        row = rows[0]
        return Template(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            thumbnail_url=row.get("thumbnail_url"),
            google_slides_template_id=row["google_slides_template_id"],
            theme=row["theme"],
            brand=json.loads(row["brand"]),
            guidelines=json.loads(row["guidelines"]),
            created_by=row["created_by"],
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    def _list_from_uc(self) -> List[Template]:
        if not self._sql_client:
            raise RuntimeError("SQL client required for UC storage")
        from config import UC_CATALOG, UC_SCHEMA
        import json

        table = f"{UC_CATALOG}.{UC_SCHEMA}.slide_templates"
        rows = self._sql_client.execute(f"SELECT * FROM {table} ORDER BY created_at DESC")
        return [
            Template(
                id=r["id"],
                name=r["name"],
                description=r["description"],
                thumbnail_url=r.get("thumbnail_url"),
                google_slides_template_id=r["google_slides_template_id"],
                theme=r["theme"],
                brand=json.loads(r["brand"]),
                guidelines=json.loads(r["guidelines"]),
                created_by=r["created_by"],
                created_at=r.get("created_at"),
                updated_at=r.get("updated_at"),
            )
            for r in rows
        ]

    def _delete_from_uc(self, template_id: str) -> None:
        if not self._sql_client:
            raise RuntimeError("SQL client required for UC storage")
        from config import UC_CATALOG, UC_SCHEMA

        table = f"{UC_CATALOG}.{UC_SCHEMA}.slide_templates"
        safe_id = self._sanitize(template_id)
        self._sql_client.execute(f"DELETE FROM {table} WHERE id = '{safe_id}'")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_template_service.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/ tests/test_template_service.py
git commit -m "feat: add template service with in-memory and UC storage"
```

---

## Task 4: Template API Endpoints

**Files:**
- Create: `backend/routers/__init__.py`
- Create: `backend/routers/templates.py`
- Modify: `backend/main.py` (add router)

- [ ] **Step 1: Write failing test**

```python
# tests/test_template_router.py
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_list_templates_empty():
    resp = client.get("/api/templates")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_create_and_get_template():
    resp = client.post("/api/templates", json={
        "name": "Test QBR",
        "description": "Test",
        "google_slides_template_id": "gslide_abc",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test QBR"
    assert "id" in data

    resp2 = client.get(f"/api/templates/{data['id']}")
    assert resp2.status_code == 200
    assert resp2.json()["name"] == "Test QBR"


def test_get_nonexistent_template():
    resp = client.get("/api/templates/nonexistent")
    assert resp.status_code == 404


def test_delete_template():
    resp = client.post("/api/templates", json={
        "name": "To Delete",
        "google_slides_template_id": "del",
    })
    tid = resp.json()["id"]
    resp2 = client.delete(f"/api/templates/{tid}")
    assert resp2.status_code == 204
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_template_router.py -v`
Expected: FAIL (404 on /api/templates)

- [ ] **Step 3: Implement router**

```python
# backend/routers/__init__.py
```

```python
# backend/routers/templates.py
from fastapi import APIRouter, HTTPException
from typing import List

from models import Template, TemplateCreate
from services.template_service import TemplateService

router = APIRouter(prefix="/api/templates", tags=["templates"])
_svc = TemplateService(use_memory=True)


@router.get("", response_model=List[Template])
def list_templates():
    return _svc.list_all()


@router.get("/{template_id}", response_model=Template)
def get_template(template_id: str):
    tpl = _svc.get(template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    return tpl


@router.post("", response_model=Template, status_code=201)
def create_template(data: TemplateCreate):
    # TODO: extract user_id from Databricks auth header in production
    return _svc.create(data, user_id="admin")


@router.delete("/{template_id}", status_code=204)
def delete_template(template_id: str):
    _svc.delete(template_id)
```

- [ ] **Step 4: Register router in main.py**

Add to `backend/main.py` after `app = FastAPI(...)`:

```python
from routers.templates import router as templates_router

app.include_router(templates_router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_template_router.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/routers/ tests/test_template_router.py backend/main.py
git commit -m "feat: add template CRUD API endpoints"
```

---

## Task 5: Dashboard Service

**Files:**
- Create: `backend/services/dashboard_service.py`
- Create: `tests/test_dashboard_service.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_dashboard_service.py
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from services.dashboard_service import DashboardService, parse_widgets_from_definition


def test_parse_widgets_from_definition():
    """Test widget extraction from a Lakeview dashboard definition."""
    definition = {
        "pages": [
            {
                "name": "page1",
                "displayName": "Overview",
                "layout": [
                    {
                        "widget": {
                            "name": "w1",
                            "textbox_spec": '{"value": "Title text"}',
                        }
                    },
                    {
                        "widget": {
                            "name": "w2",
                            "queries": [
                                {
                                    "name": "q1",
                                    "query": {
                                        "datasetName": "ds1",
                                        "fields": [
                                            {"name": "month", "expression": "`month`"},
                                            {"name": "revenue", "expression": "`revenue`"},
                                        ],
                                    },
                                }
                            ],
                            "spec": '{"version": 3, "widgetType": "bar", "encodings": {"x": {"fieldName": "month"}}}',
                        }
                    },
                ],
            }
        ]
    }
    widgets = parse_widgets_from_definition(definition)
    # Text widgets should be skipped
    assert len(widgets) == 1
    assert widgets[0].widget_id == "w2"
    assert widgets[0].viz_type == "bar"
    assert "month" in widgets[0].columns
    assert "revenue" in widgets[0].columns


def test_parse_widgets_empty():
    widgets = parse_widgets_from_definition({"pages": []})
    assert widgets == []


def test_parse_widgets_missing_spec():
    """Widget without spec should use 'unknown' viz_type."""
    definition = {
        "pages": [
            {
                "name": "p1",
                "displayName": "P1",
                "layout": [
                    {
                        "widget": {
                            "name": "w1",
                            "queries": [{"name": "q1", "query": {"datasetName": "ds1", "fields": []}}],
                        }
                    }
                ],
            }
        ]
    }
    widgets = parse_widgets_from_definition(definition)
    assert len(widgets) == 1
    assert widgets[0].viz_type == "unknown"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dashboard_service.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement dashboard service**

```python
# backend/services/dashboard_service.py
import json
from typing import Any, Dict, List, Optional

from models import DashboardInfo, WidgetInfo


def parse_widgets_from_definition(definition: Dict[str, Any]) -> List[WidgetInfo]:
    """Extract visualization widgets from a Lakeview dashboard definition."""
    widgets = []
    for page in definition.get("pages", []):
        for layout_item in page.get("layout", []):
            widget_def = layout_item.get("widget", {})
            name = widget_def.get("name", "")

            # Skip text-only widgets
            if "textbox_spec" in widget_def and "queries" not in widget_def:
                continue

            queries = widget_def.get("queries", [])
            if not queries:
                continue

            # Extract viz type from spec
            spec_str = widget_def.get("spec", "{}")
            try:
                spec = json.loads(spec_str)
                viz_type = spec.get("widgetType", "unknown")
            except (json.JSONDecodeError, TypeError):
                viz_type = "unknown"

            # Extract columns from query fields
            columns = []
            for q in queries:
                query_def = q.get("query", {})
                for field in query_def.get("fields", []):
                    col_name = field.get("name", "")
                    if col_name and col_name not in columns:
                        columns.append(col_name)

            # Extract title from spec or use widget name
            title = name
            try:
                spec = json.loads(spec_str) if spec_str else {}
                if "title" in spec:
                    title = spec["title"]
            except (json.JSONDecodeError, TypeError):
                pass

            widgets.append(
                WidgetInfo(
                    widget_id=name,
                    title=title,
                    viz_type=viz_type,
                    columns=columns,
                )
            )
    return widgets


class DashboardService:
    def __init__(self, workspace_client=None):
        self._client = workspace_client

    def list_dashboards(self) -> List[DashboardInfo]:
        """List published Lakeview dashboards accessible to the user."""
        if not self._client:
            return []
        dashboards = self._client.lakeview.list()
        return [
            DashboardInfo(
                dashboard_id=d.dashboard_id,
                name=d.display_name or d.dashboard_id,
                description="",
                updated_at=str(d.update_time) if d.update_time else None,
            )
            for d in dashboards
        ]

    def get_dashboard_definition(self, dashboard_id: str) -> Dict[str, Any]:
        """Get the published dashboard definition with widget specs."""
        if not self._client:
            return {}
        published = self._client.lakeview.get_published(dashboard_id)
        if published and published.warehouse_id:
            pass  # warehouse_id needed for query execution
        definition = {}
        if published and published.serialized_dashboard:
            definition = json.loads(published.serialized_dashboard)
        return definition

    def get_published_url(self, dashboard_id: str) -> str:
        """Get the URL for a published dashboard."""
        if not self._client:
            return ""
        host = self._client.config.host.rstrip("/")
        return f"{host}/dashboardsv3/{dashboard_id}/published"

    def execute_widget_query(
        self, dashboard_id: str, widget: WidgetInfo, warehouse_id: str
    ) -> Optional[str]:
        """Execute a widget's query and return a text summary of results."""
        # Implementation will use SQL Statements API
        # Returns a summary string like "12 rows, max revenue=$1.5M in Oct"
        # Skipped for now - will be implemented when integrating with real API
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dashboard_service.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/dashboard_service.py tests/test_dashboard_service.py
git commit -m "feat: add dashboard service with widget parsing from Lakeview API"
```

---

## Task 6: Dashboard API Endpoints

**Files:**
- Create: `backend/routers/dashboards.py`
- Modify: `backend/main.py` (add router)

- [ ] **Step 1: Write failing test**

```python
# tests/test_dashboard_router.py
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_list_dashboards():
    resp = client.get("/api/dashboards")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_dashboard_widgets():
    # Without a real Databricks connection, returns empty
    resp = client.get("/api/dashboards/fake-id/widgets")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dashboard_router.py -v`
Expected: FAIL (404)

- [ ] **Step 3: Implement router**

```python
# backend/routers/dashboards.py
from fastapi import APIRouter
from typing import List

from models import DashboardInfo, WidgetInfo
from services.dashboard_service import DashboardService, parse_widgets_from_definition

router = APIRouter(prefix="/api/dashboards", tags=["dashboards"])
_svc = DashboardService()


@router.get("", response_model=List[DashboardInfo])
def list_dashboards():
    return _svc.list_dashboards()


@router.get("/{dashboard_id}/widgets", response_model=List[WidgetInfo])
def get_dashboard_widgets(dashboard_id: str):
    definition = _svc.get_dashboard_definition(dashboard_id)
    return parse_widgets_from_definition(definition)
```

- [ ] **Step 4: Register router in main.py**

Add to `backend/main.py`:

```python
from routers.dashboards import router as dashboards_router

app.include_router(dashboards_router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_dashboard_router.py -v`
Expected: All 2 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/routers/dashboards.py tests/test_dashboard_router.py backend/main.py
git commit -m "feat: add dashboard listing and widget API endpoints"
```

---

## Task 7: Widget Capture Service (Playwright)

**Files:**
- Create: `backend/services/capture_service.py`
- Create: `tests/test_capture_service.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_capture_service.py
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from services.capture_service import CaptureService, CaptureResult


def test_capture_result_model():
    r = CaptureResult(
        widget_id="w1",
        image_path="/tmp/w1.png",
        success=True,
    )
    assert r.success
    assert r.error is None


def test_capture_result_failure():
    r = CaptureResult(
        widget_id="w2",
        image_path="",
        success=False,
        error="Timeout",
    )
    assert not r.success


def test_build_widget_selector():
    svc = CaptureService.__new__(CaptureService)
    sel = svc._build_widget_selector("widget_abc123")
    assert "widget_abc123" in sel


def test_capture_service_init():
    svc = CaptureService(
        databricks_host="https://example.databricks.com",
        databricks_token="dapi_test",
    )
    assert svc._host == "https://example.databricks.com"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_capture_service.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement capture service**

```python
# backend/services/capture_service.py
import os
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class CaptureResult:
    widget_id: str
    image_path: str
    success: bool
    error: Optional[str] = None


class CaptureService:
    WIDGET_RENDER_TIMEOUT_MS = 15_000
    PAGE_LOAD_TIMEOUT_MS = 30_000

    def __init__(self, databricks_host: str, databricks_token: str):
        self._host = databricks_host.rstrip("/")
        self._token = databricks_token

    def _build_widget_selector(self, widget_id: str) -> str:
        """Build a CSS selector for a Lakeview dashboard widget."""
        return f'[data-widget-id="{widget_id}"]'

    async def capture_widgets(
        self,
        dashboard_url: str,
        widget_ids: List[str],
        output_dir: Optional[str] = None,
    ) -> List[CaptureResult]:
        """
        Open a published dashboard in Playwright and screenshot each widget.

        Args:
            dashboard_url: Full URL to the published dashboard
            widget_ids: List of widget IDs to capture
            output_dir: Directory for PNG files (default: temp dir)

        Returns:
            List of CaptureResult with image paths or errors
        """
        if output_dir is None:
            output_dir = tempfile.mkdtemp(prefix="genie_slide_")

        results: List[CaptureResult] = []

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return [
                CaptureResult(widget_id=wid, image_path="", success=False, error="Playwright not installed")
                for wid in widget_ids
            ]

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                extra_http_headers={
                    "Authorization": f"Bearer {self._token}",
                }
            )
            page = await context.new_page()

            # Load dashboard
            try:
                await page.goto(dashboard_url, timeout=self.PAGE_LOAD_TIMEOUT_MS)
                # Wait for dashboard to finish rendering
                await page.wait_for_load_state("networkidle", timeout=self.PAGE_LOAD_TIMEOUT_MS)
            except Exception as e:
                await browser.close()
                return [
                    CaptureResult(widget_id=wid, image_path="", success=False, error=f"Dashboard load failed: {e}")
                    for wid in widget_ids
                ]

            # Capture each widget
            for wid in widget_ids:
                selector = self._build_widget_selector(wid)
                image_path = os.path.join(output_dir, f"{wid}.png")
                try:
                    element = await page.wait_for_selector(
                        selector, timeout=self.WIDGET_RENDER_TIMEOUT_MS
                    )
                    if element:
                        await element.screenshot(path=image_path)
                        results.append(CaptureResult(widget_id=wid, image_path=image_path, success=True))
                    else:
                        results.append(CaptureResult(widget_id=wid, image_path="", success=False, error="Element not found"))
                except Exception as e:
                    results.append(CaptureResult(widget_id=wid, image_path="", success=False, error=str(e)))

            await browser.close()

        return results

    def cleanup(self, results: List[CaptureResult]) -> None:
        """Delete all captured PNG files."""
        for r in results:
            if r.image_path and os.path.exists(r.image_path):
                os.remove(r.image_path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_capture_service.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/capture_service.py tests/test_capture_service.py
git commit -m "feat: add Playwright widget capture service"
```

---

## Task 8: LLM Composition Service

**Files:**
- Create: `backend/services/llm_service.py`
- Create: `tests/test_llm_service.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_llm_service.py
import pytest
import json
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from services.llm_service import LLMService, build_prompt
from models import WidgetInfo, TemplateGuidelines, TemplateBrand


def test_build_prompt_contains_all_sections():
    widgets = [
        WidgetInfo(widget_id="w1", title="Revenue", viz_type="bar_chart", columns=["month", "revenue"], row_count=12),
        WidgetInfo(widget_id="w2", title="Users", viz_type="counter", columns=["count"], row_count=1),
    ]
    guidelines = TemplateGuidelines()
    prompt = build_prompt(
        widgets=widgets,
        guidelines=guidelines,
        user_prompt="Focus on revenue growth",
        dashboard_name="Sales Dashboard",
    )
    assert "Revenue" in prompt
    assert "bar_chart" in prompt
    assert "Focus on revenue growth" in prompt
    assert "Sales Dashboard" in prompt
    assert "create-from-spec" in prompt
    assert "title" in prompt  # must_include layout
    assert "closing" in prompt


def test_build_prompt_without_user_prompt():
    widgets = [
        WidgetInfo(widget_id="w1", title="KPI", viz_type="counter", columns=["val"], row_count=1),
    ]
    guidelines = TemplateGuidelines()
    prompt = build_prompt(widgets=widgets, guidelines=guidelines, dashboard_name="Test")
    assert "KPI" in prompt
    # Should not have empty user instruction section
    assert "User instruction" not in prompt or "None" not in prompt


def test_build_prompt_includes_widget_summaries():
    widgets = [
        WidgetInfo(
            widget_id="w1",
            title="Revenue",
            viz_type="bar_chart",
            columns=["month", "revenue"],
            row_count=12,
            query_result_summary="12 rows. Max revenue: $1.5M (Oct). Min: $0.8M (Feb).",
        ),
    ]
    guidelines = TemplateGuidelines()
    prompt = build_prompt(widgets=widgets, guidelines=guidelines, dashboard_name="Sales")
    assert "$1.5M" in prompt


def test_parse_llm_response_valid_json():
    svc = LLMService.__new__(LLMService)
    raw = '''Here is the slide spec:
```json
[{"layout": "title", "title": "Hello"}]
```
'''
    result = svc._parse_response(raw)
    assert len(result) == 1
    assert result[0]["layout"] == "title"


def test_parse_llm_response_raw_json():
    svc = LLMService.__new__(LLMService)
    raw = '[{"layout": "closing"}]'
    result = svc._parse_response(raw)
    assert result[0]["layout"] == "closing"


def test_parse_llm_response_invalid():
    svc = LLMService.__new__(LLMService)
    with pytest.raises(ValueError):
        svc._parse_response("This is not JSON at all")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_llm_service.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement LLM service**

```python
# backend/services/llm_service.py
import json
import re
from typing import Any, Dict, List, Optional

from models import WidgetInfo, TemplateGuidelines

AVAILABLE_LAYOUTS = """Available layouts (from gslides_builder.py create-from-spec):
- title: Title slide (fields: title, subtitle)
- content_basic: Title + body text (fields: title, body, bullets)
- content_subtitle: Title + subtitle + body (fields: title, subtitle, body, bullets)
- content_2col: Two columns (fields: title, columns[4]: col1_header, col1_body, col2_header, col2_body)
- content_3col: Three columns (fields: title, columns[6]: header1, body1, header2, body2, header3, body3)
- title_only: Title only, good for tables/charts (fields: title, table)
- section_break_1 to section_break_6: Section dividers (fields: title)
- content_basic_dark: Dark background content (fields: title, body, bullets)
- quote_dark: Quote on dark background (fields: title as quote text, subtitle as attribution)
- closing: Closing slide (no fields)
- blank: Blank slide

For chart widgets, use title_only layout and set "_widget_id" to reference the widget.
For two charts side-by-side, use a slide with "_left_widget_id" and "_right_widget_id".
Table field format: {"data": [["Header1","Header2"],["val1","val2"]], "y": 1.8, "width": 11.5, "height": 4.0}
"""


def build_prompt(
    widgets: List[WidgetInfo],
    guidelines: TemplateGuidelines,
    dashboard_name: str,
    user_prompt: Optional[str] = None,
) -> str:
    """Build the LLM prompt for slide composition."""
    widget_descriptions = []
    for w in widgets:
        desc = f"- ID: {w.widget_id} | Title: {w.title} | Type: {w.viz_type} | Columns: {', '.join(w.columns)} | Rows: {w.row_count}"
        if w.query_result_summary:
            desc += f"\n  Data summary: {w.query_result_summary}"
        widget_descriptions.append(desc)

    widgets_section = "\n".join(widget_descriptions) if widget_descriptions else "(No visualization widgets found)"

    prompt = f"""You are a presentation designer. Create a slide deck spec from a dashboard.

## Dashboard: {dashboard_name}

### Widgets available:
{widgets_section}

### Template guidelines:
- Slide count: {guidelines.total_slides_min} to {guidelines.total_slides_max}
- Structure: {guidelines.structure_hint}
- Preferred layouts: {', '.join(guidelines.preferred_layouts)}
- Style: {guidelines.style_notes}
- Must include: {', '.join(guidelines.must_include)}
- Chart preference: {guidelines.chart_preference}

{AVAILABLE_LAYOUTS}

## Instructions:
1. Analyze the dashboard widgets and create a narrative slide deck.
2. Map widgets to appropriate slides using "_widget_id" fields.
3. Generate insightful titles and text (not just widget titles).
4. Structure slides to tell a coherent story.
5. Output ONLY a JSON array in create-from-spec format. No other text."""

    if user_prompt:
        prompt += f"""

## User direction:
{user_prompt}"""

    return prompt


class LLMService:
    def __init__(self, workspace_client=None):
        self._client = workspace_client

    async def compose_slides(
        self,
        widgets: List[WidgetInfo],
        guidelines: TemplateGuidelines,
        dashboard_name: str,
        user_prompt: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Call Foundation Model API to generate slide spec JSON."""
        prompt = build_prompt(widgets, guidelines, dashboard_name, user_prompt)

        if not self._client:
            raise RuntimeError("Workspace client required for LLM calls")

        response = self._client.serving_endpoints.query(
            name="databricks-claude-sonnet-4",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=0.3,
        )

        raw_text = response.choices[0].message.content
        return self._parse_response(raw_text)

    def _parse_response(self, raw: str) -> List[Dict[str, Any]]:
        """Extract JSON array from LLM response text."""
        # Try extracting from markdown code block
        match = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
        if match:
            raw = match.group(1).strip()

        # Try parsing as JSON directly
        raw = raw.strip()
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
            raise ValueError("LLM response is not a JSON array")
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse LLM response as JSON: {e}\nRaw: {raw[:500]}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_llm_service.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/llm_service.py tests/test_llm_service.py
git commit -m "feat: add LLM composition service with prompt builder"
```

---

## Task 9: Google Auth Service

**Files:**
- Create: `backend/services/google_auth_service.py`
- Create: `backend/routers/auth.py`
- Modify: `backend/main.py` (add router)

- [ ] **Step 1: Write test**

```python
# tests/test_google_auth.py
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from services.google_auth_service import GoogleAuthService, build_auth_url


def test_build_auth_url():
    url = build_auth_url(
        client_id="test_client_id",
        redirect_uri="http://localhost:8000/api/auth/google/callback",
        state="abc123",
    )
    assert "test_client_id" in url
    assert "redirect_uri" in url
    assert "abc123" in url
    assert "https://www.googleapis.com/auth/presentations" in url
    assert "https://www.googleapis.com/auth/drive.file" in url


def test_google_auth_service_init():
    svc = GoogleAuthService(client_id="cid", client_secret="csecret")
    assert svc._client_id == "cid"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_google_auth.py -v`
Expected: FAIL

- [ ] **Step 3: Implement Google auth service**

```python
# backend/services/google_auth_service.py
from urllib.parse import urlencode
from typing import Optional
import httpx

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = [
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/drive.file",
]


def build_auth_url(client_id: str, redirect_uri: str, state: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "state": state,
        "prompt": "consent",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


class GoogleAuthService:
    def __init__(self, client_id: str, client_secret: str):
        self._client_id = client_id
        self._client_secret = client_secret

    async def exchange_code(self, code: str, redirect_uri: str) -> dict:
        """Exchange authorization code for access token."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def refresh_token(self, refresh_token: str) -> dict:
        """Refresh an expired access token."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            resp.raise_for_status()
            return resp.json()
```

```python
# backend/routers/auth.py
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
import uuid

from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
from services.google_auth_service import GoogleAuthService, build_auth_url

router = APIRouter(prefix="/api/auth", tags=["auth"])
_svc = GoogleAuthService(client_id=GOOGLE_CLIENT_ID, client_secret=GOOGLE_CLIENT_SECRET)


@router.get("/google/login")
def google_login(request: Request):
    state = str(uuid.uuid4())
    redirect_uri = str(request.base_url) + "api/auth/google/callback"
    url = build_auth_url(GOOGLE_CLIENT_ID, redirect_uri, state)
    response = RedirectResponse(url)
    response.set_cookie("oauth_state", state, httponly=True, max_age=600)
    return response


@router.get("/google/callback")
async def google_callback(request: Request, code: str, state: str):
    # Validate state to prevent CSRF
    expected_state = request.cookies.get("oauth_state")
    if not expected_state or state != expected_state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state. Please retry login.")

    redirect_uri = str(request.base_url) + "api/auth/google/callback"
    tokens = await _svc.exchange_code(code, redirect_uri)
    response = RedirectResponse("/")
    # Clear the one-time state cookie
    response.delete_cookie("oauth_state")
    response.set_cookie(
        "google_access_token",
        tokens["access_token"],
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=tokens.get("expires_in", 3600),
    )
    if "refresh_token" in tokens:
        response.set_cookie(
            "google_refresh_token",
            tokens["refresh_token"],
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=86400 * 30,
        )
    return response


@router.get("/google/status")
def google_status(request: Request):
    token = request.cookies.get("google_access_token")
    return {"authenticated": token is not None}
```

- [ ] **Step 4: Register router in main.py**

Add to `backend/main.py`:

```python
from routers.auth import router as auth_router

app.include_router(auth_router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_google_auth.py -v`
Expected: All 2 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/services/google_auth_service.py backend/routers/auth.py tests/test_google_auth.py backend/main.py
git commit -m "feat: add Google OAuth service and auth endpoints"
```

---

## Task 10: Slides Generation Service

**Files:**
- Create: `backend/services/slides_service.py`
- Create: `tests/test_slides_service.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_slides_service.py
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from services.slides_service import SlidesService, extract_widget_refs


def test_extract_widget_refs():
    spec = [
        {"layout": "title", "title": "Hello"},
        {"layout": "title_only", "title": "Chart", "_widget_id": "w1"},
        {"layout": "content_2col", "title": "Compare", "_left_widget_id": "w2", "_right_widget_id": "w3"},
        {"layout": "closing"},
    ]
    refs = extract_widget_refs(spec)
    assert refs == {
        1: {"_widget_id": "w1"},
        2: {"_left_widget_id": "w2", "_right_widget_id": "w3"},
    }


def test_extract_widget_refs_empty():
    spec = [{"layout": "title", "title": "No charts"}]
    refs = extract_widget_refs(spec)
    assert refs == {}


def test_clean_spec_for_builder():
    svc = SlidesService.__new__(SlidesService)
    spec = [
        {"layout": "title", "title": "Hello"},
        {"layout": "title_only", "title": "Chart", "_widget_id": "w1"},
    ]
    cleaned = svc._clean_spec(spec)
    assert "_widget_id" not in cleaned[1]
    assert cleaned[1]["layout"] == "title_only"
    assert cleaned[0]["title"] == "Hello"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_slides_service.py -v`
Expected: FAIL

- [ ] **Step 3: Implement slides service**

```python
# backend/services/slides_service.py
import copy
import importlib.util
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

from config import GSLIDES_BUILDER_PATH

WIDGET_REF_KEYS = ("_widget_id", "_left_widget_id", "_right_widget_id")


def extract_widget_refs(spec: List[Dict[str, Any]]) -> Dict[int, Dict[str, str]]:
    """Extract widget ID references from slide spec, keyed by slide index."""
    refs = {}
    for i, slide in enumerate(spec):
        slide_refs = {}
        for key in WIDGET_REF_KEYS:
            if key in slide:
                slide_refs[key] = slide[key]
        if slide_refs:
            refs[i] = slide_refs
    return refs


def _load_gslides_builder():
    """Dynamically import gslides_builder.py."""
    spec = importlib.util.spec_from_file_location("gslides_builder", GSLIDES_BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load gslides_builder from {GSLIDES_BUILDER_PATH}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class SlidesService:
    def __init__(self, google_access_token: str):
        self._token = google_access_token

    def _clean_spec(self, spec: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove _widget_id keys before passing to gslides_builder."""
        cleaned = []
        for slide in spec:
            s = {k: v for k, v in slide.items() if k not in WIDGET_REF_KEYS}
            cleaned.append(s)
        return cleaned

    def generate(
        self,
        title: str,
        spec: List[Dict[str, Any]],
        template_id: str,
        theme: str = "light",
        widget_images: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a Google Slides presentation from a spec.

        Args:
            title: Presentation title
            spec: Slide spec (create-from-spec format with _widget_id refs)
            template_id: Google Slides template to copy
            theme: "light" or "dark"
            widget_images: Map of widget_id -> Google Drive image URL

        Returns:
            Dict with presentationId, url, slideIds
        """
        builder = _load_gslides_builder()

        # Patch the access token to use our per-user OAuth token
        original_get_token = builder.get_access_token
        builder.get_access_token = lambda: self._token
        builder._access_token_cache = (self._token, __import__("time").time())

        widget_refs = extract_widget_refs(spec)
        clean_spec = self._clean_spec(spec)

        try:
            result = builder.create_presentation_from_spec(
                title=title,
                slides=clean_spec,
                template_id=template_id,
                theme=theme,
            )

            # Insert widget images into corresponding slides
            if widget_images and result.get("slideIds"):
                slide_ids = result["slideIds"]
                pres_id = result["presentationId"]

                for slide_idx, refs in widget_refs.items():
                    if slide_idx >= len(slide_ids):
                        continue
                    page_id = slide_ids[slide_idx]

                    for ref_key, widget_id in refs.items():
                        image_url = widget_images.get(widget_id)
                        if not image_url:
                            continue

                        # Position depends on single vs side-by-side
                        if ref_key == "_widget_id":
                            builder.create_image(
                                pres_id, page_id, image_url,
                                x=0.5, y=1.8, width=11.5, height=5.0,
                            )
                        elif ref_key == "_left_widget_id":
                            builder.create_image(
                                pres_id, page_id, image_url,
                                x=0.3, y=1.8, width=5.8, height=4.5,
                            )
                        elif ref_key == "_right_widget_id":
                            builder.create_image(
                                pres_id, page_id, image_url,
                                x=6.3, y=1.8, width=5.8, height=4.5,
                            )

            return result
        finally:
            builder.get_access_token = original_get_token
            builder._access_token_cache = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_slides_service.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/slides_service.py tests/test_slides_service.py
git commit -m "feat: add slides generation service wrapping gslides_builder.py"
```

---

## Task 11: Generation Orchestrator & API Endpoint

**Files:**
- Create: `backend/routers/generation.py`
- Create: `tests/test_generation_router.py`
- Modify: `backend/main.py` (add router)

- [ ] **Step 1: Write failing test**

```python
# tests/test_generation_router.py
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_generate_requires_valid_template():
    resp = client.post("/api/generate", json={
        "template_id": "nonexistent",
        "dashboard_id": "dash1",
    })
    assert resp.status_code == 404
    assert "Template" in resp.json()["detail"]


def test_generate_endpoint_exists():
    resp = client.post("/api/generate", json={
        "template_id": "test",
        "dashboard_id": "test",
    })
    # Should return 404 (template not found), not 405 (method not allowed)
    assert resp.status_code != 405
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_generation_router.py -v`
Expected: FAIL (404 on /api/generate — endpoint doesn't exist)

- [ ] **Step 3: Implement generation router**

```python
# backend/routers/generation.py
import os
import tempfile
from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Optional

from models import GenerationRequest, GenerationResult, WidgetInfo
from services.template_service import TemplateService
from services.dashboard_service import DashboardService, parse_widgets_from_definition
from services.capture_service import CaptureService
from services.llm_service import LLMService
from services.slides_service import SlidesService
import config

router = APIRouter(prefix="/api", tags=["generation"])
_template_svc = TemplateService(use_memory=True)


@router.post("/generate", response_model=GenerationResult)
async def generate_slides(req: GenerationRequest, request: Request):
    # 1. Validate template
    template = _template_svc.get(req.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # 2. Check Google auth
    google_token = request.cookies.get("google_access_token")
    if not google_token:
        raise HTTPException(status_code=401, detail="Google authentication required. Visit /api/auth/google/login")

    # 3. Get dashboard data
    try:
        from databricks.sdk import WorkspaceClient

        ws = WorkspaceClient()
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to connect to Databricks workspace")

    dash_svc = DashboardService(workspace_client=ws)
    definition = dash_svc.get_dashboard_definition(req.dashboard_id)
    if not definition:
        raise HTTPException(status_code=404, detail="Dashboard not found or not published")

    widgets = parse_widgets_from_definition(definition)
    dashboard_url = dash_svc.get_published_url(req.dashboard_id)

    # 4. Capture widget images
    warnings = []
    widget_images: Dict[str, str] = {}
    capture_results = []

    if widgets:
        capture_svc = CaptureService(
            databricks_host=config.DATABRICKS_HOST,
            databricks_token=config.DATABRICKS_TOKEN,
        )
        capture_results = await capture_svc.capture_widgets(
            dashboard_url=dashboard_url,
            widget_ids=[w.widget_id for w in widgets],
        )

        skipped = []
        for cr in capture_results:
            if not cr.success:
                skipped.append(cr.widget_id)
                warnings.append(f"Widget '{cr.widget_id}' skipped: {cr.error}")
            # Mark widget capture status
            for w in widgets:
                if w.widget_id == cr.widget_id:
                    w.capture_status = "captured" if cr.success else "capture_failed"

    # 5. LLM composition
    llm_svc = LLMService(workspace_client=ws)
    try:
        # Get dashboard name from definition
        dash_name = definition.get("displayName", req.dashboard_id)
        slide_spec = await llm_svc.compose_slides(
            widgets=[w for w in widgets if w.capture_status == "captured"],
            guidelines=template.guidelines,
            dashboard_name=dash_name,
            user_prompt=req.user_prompt,
        )
    except Exception as e:
        # Cleanup captured images before raising
        if capture_results:
            CaptureService(databricks_host="", databricks_token="").cleanup(capture_results)
        raise HTTPException(status_code=500, detail=f"Slide composition failed: {e}")

    # 6. Upload captured images to Google Drive and get URLs
    # (Upload PNGs, get public URLs, then delete from Drive after insertion)
    for cr in capture_results:
        if cr.success and cr.image_path:
            try:
                url = await _upload_to_drive(cr.image_path, cr.widget_id, google_token)
                widget_images[cr.widget_id] = url
            except Exception as e:
                warnings.append(f"Image upload failed for '{cr.widget_id}': {e}")

    # 7. Generate Google Slides
    slides_svc = SlidesService(google_access_token=google_token)
    try:
        result = slides_svc.generate(
            title=f"{definition.get('displayName', 'Dashboard')} Presentation",
            spec=slide_spec,
            template_id=template.google_slides_template_id,
            theme=template.theme,
            widget_images=widget_images,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Slides generation failed: {e}")
    finally:
        # Cleanup temp images
        if capture_results:
            CaptureService(databricks_host="", databricks_token="").cleanup(capture_results)

    return GenerationResult(
        google_slides_url=result.get("url", ""),
        slide_count=len(result.get("slideIds", [])),
        warnings=warnings,
        skipped_widgets=skipped if widgets else [],
    )


async def _upload_to_drive(image_path: str, name: str, token: str) -> str:
    """Upload a PNG to Google Drive and return a URL usable by Slides API."""
    import httpx

    boundary = "----GenieSlideUpload"
    filename = f"{name}.png"

    with open(image_path, "rb") as f:
        image_data = f.read()

    metadata = f'{{"name": "{filename}", "mimeType": "image/png"}}'
    body = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{metadata}\r\n"
        f"--{boundary}\r\nContent-Type: image/png\r\n\r\n"
    ).encode() + image_data + f"\r\n--{boundary}--".encode()

    async with httpx.AsyncClient() as client:
        # Upload file
        resp = await client.post(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": f"multipart/related; boundary={boundary}",
            },
            content=body,
        )
        resp.raise_for_status()
        file_id = resp.json()["id"]

        # The uploaded file is owned by the user's Google account (via their OAuth token).
        # The Slides API can reference images from the same user's Drive without
        # additional permissions. No public sharing is needed.
        # Return the Drive content URI that the Slides API accepts for same-owner images.
        return f"https://lh3.google.com/d/{file_id}"
```

- [ ] **Step 4: Register router in main.py**

Add to `backend/main.py`:

```python
from routers.generation import router as generation_router

app.include_router(generation_router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_generation_router.py -v`
Expected: All 2 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/routers/generation.py tests/test_generation_router.py backend/main.py
git commit -m "feat: add generation orchestrator with end-to-end pipeline"
```

---

## Task 12: Frontend Types & API Client

**Files:**
- Create: `frontend/src/types.ts`
- Create: `frontend/src/api.ts`

- [ ] **Step 1: Create types**

```typescript
// frontend/src/types.ts
export interface TemplateBrand {
  primary: string;
  secondary: string;
  accent: string;
  text_dark: string;
  text_light: string;
  font: string;
}

export interface TemplateGuidelines {
  total_slides_min: number;
  total_slides_max: number;
  structure_hint: string;
  preferred_layouts: string[];
  style_notes: string;
  must_include: string[];
  chart_preference: string;
}

export interface Template {
  id: string;
  name: string;
  description: string;
  thumbnail_url: string | null;
  google_slides_template_id: string;
  theme: string;
  brand: TemplateBrand;
  guidelines: TemplateGuidelines;
  created_by: string;
  created_at: string | null;
}

export interface TemplateCreate {
  name: string;
  description?: string;
  google_slides_template_id: string;
  theme?: string;
  brand?: Partial<TemplateBrand>;
  guidelines?: Partial<TemplateGuidelines>;
}

export interface DashboardInfo {
  dashboard_id: string;
  name: string;
  description: string;
  widget_count: number;
  updated_at: string | null;
}

export interface GenerationRequest {
  template_id: string;
  dashboard_id: string;
  user_prompt?: string;
}

export interface GenerationResult {
  google_slides_url: string;
  slide_count: number;
  warnings: string[];
  skipped_widgets: string[];
}

export interface GoogleAuthStatus {
  authenticated: boolean;
}
```

- [ ] **Step 2: Create API client**

```typescript
// frontend/src/api.ts
import type {
  Template,
  TemplateCreate,
  DashboardInfo,
  GenerationRequest,
  GenerationResult,
  GoogleAuthStatus,
} from "./types";

const BASE = "/api";

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, init);
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || resp.statusText);
  }
  if (resp.status === 204) return undefined as unknown as T;
  return resp.json();
}

export const api = {
  // Templates
  listTemplates: () => fetchJson<Template[]>(`${BASE}/templates`),

  getTemplate: (id: string) => fetchJson<Template>(`${BASE}/templates/${id}`),

  createTemplate: (data: TemplateCreate) =>
    fetchJson<Template>(`${BASE}/templates`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),

  deleteTemplate: (id: string) =>
    fetchJson<void>(`${BASE}/templates/${id}`, { method: "DELETE" }),

  // Dashboards
  listDashboards: () => fetchJson<DashboardInfo[]>(`${BASE}/dashboards`),

  // Generation
  generate: (req: GenerationRequest) =>
    fetchJson<GenerationResult>(`${BASE}/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }),

  // Auth
  googleAuthStatus: () => fetchJson<GoogleAuthStatus>(`${BASE}/auth/google/status`),
};
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types.ts frontend/src/api.ts
git commit -m "feat: add frontend TypeScript types and API client"
```

---

## Task 13: Frontend - Template Selection (Home Page)

**Files:**
- Create: `frontend/src/pages/HomePage.tsx`
- Create: `frontend/src/components/TemplateCard.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create TemplateCard component**

```tsx
// frontend/src/components/TemplateCard.tsx
import type { Template } from "../types";

interface Props {
  template: Template;
  onSelect: (template: Template) => void;
}

export default function TemplateCard({ template, onSelect }: Props) {
  return (
    <div
      onClick={() => onSelect(template)}
      style={{
        border: "1px solid #ddd",
        borderRadius: 8,
        padding: 16,
        cursor: "pointer",
        transition: "box-shadow 0.2s",
      }}
      onMouseEnter={(e) => (e.currentTarget.style.boxShadow = "0 2px 8px rgba(0,0,0,0.1)")}
      onMouseLeave={(e) => (e.currentTarget.style.boxShadow = "none")}
    >
      <h3 style={{ margin: "0 0 8px" }}>{template.name}</h3>
      <p style={{ margin: "0 0 8px", color: "#666", fontSize: 14 }}>
        {template.description || "No description"}
      </p>
      <div style={{ fontSize: 12, color: "#999" }}>
        {template.guidelines.total_slides_min}-{template.guidelines.total_slides_max} slides
        &middot; {template.theme}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create HomePage**

```tsx
// frontend/src/pages/HomePage.tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import type { Template } from "../types";
import TemplateCard from "../components/TemplateCard";

export default function HomePage() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    api
      .listTemplates()
      .then(setTemplates)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const handleSelect = (template: Template) => {
    navigate(`/dashboard-select?template=${template.id}`);
  };

  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: 32 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <h1 style={{ margin: 0 }}>Genie Slide</h1>
        <button
          onClick={() => navigate("/admin/template")}
          style={{ padding: "8px 16px", cursor: "pointer" }}
        >
          + Template
        </button>
      </div>
      <p style={{ color: "#666", marginBottom: 24 }}>
        Select a template to generate a presentation from your dashboard.
      </p>
      {loading && <p>Loading templates...</p>}
      {error && <p style={{ color: "red" }}>{error}</p>}
      {!loading && templates.length === 0 && (
        <p>No templates registered. Click "+ Template" to create one.</p>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 16 }}>
        {templates.map((t) => (
          <TemplateCard key={t.id} template={t} onSelect={handleSelect} />
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Update App.tsx with routes**

```tsx
// frontend/src/App.tsx
import { Routes, Route } from "react-router-dom";
import HomePage from "./pages/HomePage";

function Placeholder({ name }: { name: string }) {
  return <div style={{ padding: 32 }}><h1>{name}</h1><p>Coming soon</p></div>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/dashboard-select" element={<Placeholder name="Select Dashboard" />} />
      <Route path="/generate" element={<Placeholder name="Generate" />} />
      <Route path="/admin/template" element={<Placeholder name="Register Template" />} />
    </Routes>
  );
}
```

- [ ] **Step 4: Verify build**

Run: `cd frontend && npm install && npm run build`
Expected: Build succeeds with no errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/
git commit -m "feat: add home page with template selection grid"
```

---

## Task 14: Frontend - Dashboard Selection Page

**Files:**
- Create: `frontend/src/pages/DashboardSelectPage.tsx`
- Create: `frontend/src/components/DashboardList.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create DashboardList component**

```tsx
// frontend/src/components/DashboardList.tsx
import type { DashboardInfo } from "../types";

interface Props {
  dashboards: DashboardInfo[];
  onSelect: (dashboard: DashboardInfo) => void;
  filter: string;
}

export default function DashboardList({ dashboards, onSelect, filter }: Props) {
  const filtered = dashboards.filter(
    (d) => d.name.toLowerCase().includes(filter.toLowerCase())
  );

  if (filtered.length === 0) {
    return <p style={{ color: "#666" }}>No dashboards found.</p>;
  }

  return (
    <div>
      {filtered.map((d) => (
        <div
          key={d.dashboard_id}
          onClick={() => onSelect(d)}
          style={{
            padding: "12px 16px",
            border: "1px solid #eee",
            borderRadius: 6,
            marginBottom: 8,
            cursor: "pointer",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "#f8f8f8")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "white")}
        >
          <div style={{ fontWeight: 500 }}>{d.name}</div>
          {d.description && <div style={{ fontSize: 13, color: "#666" }}>{d.description}</div>}
          {d.updated_at && <div style={{ fontSize: 12, color: "#999" }}>Updated: {d.updated_at}</div>}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Create DashboardSelectPage**

```tsx
// frontend/src/pages/DashboardSelectPage.tsx
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import type { DashboardInfo } from "../types";
import DashboardList from "../components/DashboardList";

export default function DashboardSelectPage() {
  const [dashboards, setDashboards] = useState<DashboardInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const templateId = searchParams.get("template") || "";

  useEffect(() => {
    api
      .listDashboards()
      .then(setDashboards)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const handleSelect = (dashboard: DashboardInfo) => {
    navigate(`/generate?template=${templateId}&dashboard=${dashboard.dashboard_id}`);
  };

  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: 32 }}>
      <button onClick={() => navigate("/")} style={{ marginBottom: 16, cursor: "pointer" }}>
        &larr; Back
      </button>
      <h1>Select Dashboard</h1>
      <input
        type="text"
        placeholder="Search dashboards..."
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        style={{ width: "100%", padding: "8px 12px", marginBottom: 16, border: "1px solid #ddd", borderRadius: 6 }}
      />
      {loading && <p>Loading dashboards...</p>}
      {error && <p style={{ color: "red" }}>{error}</p>}
      {!loading && <DashboardList dashboards={dashboards} onSelect={handleSelect} filter={filter} />}
    </div>
  );
}
```

- [ ] **Step 3: Update App.tsx**

Replace the dashboard-select placeholder route in `App.tsx`:

```tsx
import DashboardSelectPage from "./pages/DashboardSelectPage";

// In Routes:
<Route path="/dashboard-select" element={<DashboardSelectPage />} />
```

- [ ] **Step 4: Verify build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
git add frontend/src/
git commit -m "feat: add dashboard selection page with search"
```

---

## Task 15: Frontend - Generate Page (Settings + Progress + Result)

**Files:**
- Create: `frontend/src/pages/GeneratePage.tsx`
- Create: `frontend/src/components/ProgressIndicator.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create ProgressIndicator**

```tsx
// frontend/src/components/ProgressIndicator.tsx
interface Props {
  step: number;  // 0-based
  steps: string[];
}

export default function ProgressIndicator({ step, steps }: Props) {
  return (
    <div style={{ display: "flex", gap: 8, marginBottom: 24 }}>
      {steps.map((label, i) => (
        <div key={i} style={{ flex: 1, textAlign: "center" }}>
          <div
            style={{
              height: 4,
              borderRadius: 2,
              background: i <= step ? "#0066CC" : "#ddd",
              marginBottom: 4,
              transition: "background 0.3s",
            }}
          />
          <span style={{ fontSize: 12, color: i <= step ? "#0066CC" : "#999" }}>{label}</span>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Create GeneratePage**

```tsx
// frontend/src/pages/GeneratePage.tsx
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import type { GenerationResult } from "../types";
import ProgressIndicator from "../components/ProgressIndicator";

const STEPS = ["Capture widgets", "Compose slides", "Generate presentation", "Done"];

export default function GeneratePage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const templateId = searchParams.get("template") || "";
  const dashboardId = searchParams.get("dashboard") || "";

  const [prompt, setPrompt] = useState("");
  const [generating, setGenerating] = useState(false);
  const [step, setStep] = useState(-1);
  const [result, setResult] = useState<GenerationResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = async () => {
    setGenerating(true);
    setError(null);
    setStep(0);

    try {
      // Simulate step progress (actual steps happen server-side)
      const stepTimer = setInterval(() => {
        setStep((s) => Math.min(s + 1, 2));
      }, 5000);

      const res = await api.generate({
        template_id: templateId,
        dashboard_id: dashboardId,
        user_prompt: prompt || undefined,
      });

      clearInterval(stepTimer);
      setStep(3);
      setResult(res);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: 32 }}>
      <button onClick={() => navigate(-1)} style={{ marginBottom: 16, cursor: "pointer" }}>
        &larr; Back
      </button>
      <h1>Generate Presentation</h1>

      {!generating && !result && (
        <>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: "block", marginBottom: 4, fontWeight: 500 }}>
              Prompt (optional)
            </label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="e.g. Focus on NA region growth. Keep it concise for executives."
              style={{
                width: "100%",
                minHeight: 80,
                padding: "8px 12px",
                border: "1px solid #ddd",
                borderRadius: 6,
                resize: "vertical",
              }}
            />
          </div>
          <button
            onClick={handleGenerate}
            style={{
              padding: "12px 32px",
              background: "#0066CC",
              color: "white",
              border: "none",
              borderRadius: 6,
              cursor: "pointer",
              fontSize: 16,
            }}
          >
            Generate Slides
          </button>
        </>
      )}

      {generating && (
        <div>
          <ProgressIndicator step={step} steps={STEPS} />
          <p style={{ textAlign: "center", color: "#666" }}>
            {step >= 0 && step < STEPS.length ? STEPS[step] + "..." : "Preparing..."}
          </p>
        </div>
      )}

      {error && (
        <div style={{ padding: 16, background: "#FEE", borderRadius: 6, marginTop: 16 }}>
          <p style={{ color: "red", margin: 0 }}>{error}</p>
          <button onClick={() => { setError(null); setResult(null); setStep(-1); }} style={{ marginTop: 8, cursor: "pointer" }}>
            Try Again
          </button>
        </div>
      )}

      {result && (
        <div style={{ marginTop: 24 }}>
          <div style={{ padding: 24, background: "#F0FFF0", borderRadius: 8, marginBottom: 16 }}>
            <h2 style={{ margin: "0 0 8px", color: "#0a0" }}>Presentation Ready!</h2>
            <p style={{ margin: "0 0 16px" }}>{result.slide_count} slides created</p>
            <a
              href={result.google_slides_url}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: "inline-block",
                padding: "12px 24px",
                background: "#0066CC",
                color: "white",
                borderRadius: 6,
                textDecoration: "none",
              }}
            >
              Open in Google Slides
            </a>
          </div>
          {result.warnings.length > 0 && (
            <div style={{ padding: 12, background: "#FFF8E0", borderRadius: 6 }}>
              <strong>Warnings:</strong>
              <ul>
                {result.warnings.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            </div>
          )}
          <div style={{ marginTop: 16, display: "flex", gap: 8 }}>
            <button onClick={() => { setResult(null); setStep(-1); }} style={{ cursor: "pointer" }}>
              Regenerate
            </button>
            <button onClick={() => navigate("/")} style={{ cursor: "pointer" }}>
              New Presentation
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Update App.tsx**

```tsx
import GeneratePage from "./pages/GeneratePage";

// In Routes:
<Route path="/generate" element={<GeneratePage />} />
```

- [ ] **Step 4: Verify build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
git add frontend/src/
git commit -m "feat: add generation page with progress and result display"
```

---

## Task 16: Frontend - Admin Template Registration

**Files:**
- Create: `frontend/src/pages/AdminTemplatePage.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create AdminTemplatePage**

```tsx
// frontend/src/pages/AdminTemplatePage.tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

export default function AdminTemplatePage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [theme, setTheme] = useState("light");
  const [primaryColor, setPrimaryColor] = useState("#333333");
  const [font, setFont] = useState("Noto Sans JP");
  const [slidesMin, setSlidesMin] = useState(6);
  const [slidesMax, setSlidesMax] = useState(12);
  const [structureHint, setStructureHint] = useState("Overview → Data detail → Insights → Next actions");
  const [styleNotes, setStyleNotes] = useState("Concise. One message per slide.");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = async () => {
    if (!name || !templateId) {
      setError("Name and Google Slides Template ID are required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.createTemplate({
        name,
        description,
        google_slides_template_id: templateId,
        theme,
        brand: { primary: primaryColor, font },
        guidelines: {
          total_slides_min: slidesMin,
          total_slides_max: slidesMax,
          structure_hint: structureHint,
          style_notes: styleNotes,
        },
      });
      navigate("/");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const fieldStyle = { width: "100%", padding: "8px 12px", border: "1px solid #ddd", borderRadius: 6, marginBottom: 16 };
  const labelStyle = { display: "block" as const, marginBottom: 4, fontWeight: 500 as const };

  return (
    <div style={{ maxWidth: 640, margin: "0 auto", padding: 32 }}>
      <button onClick={() => navigate("/")} style={{ marginBottom: 16, cursor: "pointer" }}>&larr; Back</button>
      <h1>Register Template</h1>

      <label style={labelStyle}>Name *</label>
      <input value={name} onChange={(e) => setName(e.target.value)} style={fieldStyle} placeholder="Quarterly Business Review" />

      <label style={labelStyle}>Description</label>
      <input value={description} onChange={(e) => setDescription(e.target.value)} style={fieldStyle} placeholder="Standard QBR template" />

      <label style={labelStyle}>Google Slides Template ID *</label>
      <input value={templateId} onChange={(e) => setTemplateId(e.target.value)} style={fieldStyle} placeholder="1abc...xyz (from template URL)" />

      <label style={labelStyle}>Theme</label>
      <select value={theme} onChange={(e) => setTheme(e.target.value)} style={fieldStyle}>
        <option value="light">Light</option>
        <option value="dark">Dark</option>
      </select>

      <label style={labelStyle}>Primary Brand Color</label>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <input type="color" value={primaryColor} onChange={(e) => setPrimaryColor(e.target.value)} />
        <input value={primaryColor} onChange={(e) => setPrimaryColor(e.target.value)} style={{ ...fieldStyle, marginBottom: 0 }} />
      </div>

      <label style={labelStyle}>Font</label>
      <input value={font} onChange={(e) => setFont(e.target.value)} style={fieldStyle} />

      <label style={labelStyle}>Slide Count Range</label>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <input type="number" value={slidesMin} onChange={(e) => setSlidesMin(+e.target.value)} style={{ ...fieldStyle, width: 80, marginBottom: 0 }} />
        <span style={{ alignSelf: "center" }}>to</span>
        <input type="number" value={slidesMax} onChange={(e) => setSlidesMax(+e.target.value)} style={{ ...fieldStyle, width: 80, marginBottom: 0 }} />
      </div>

      <label style={labelStyle}>Structure Hint</label>
      <input value={structureHint} onChange={(e) => setStructureHint(e.target.value)} style={fieldStyle} />

      <label style={labelStyle}>Style Notes</label>
      <textarea value={styleNotes} onChange={(e) => setStyleNotes(e.target.value)} style={{ ...fieldStyle, minHeight: 60 }} />

      {error && <p style={{ color: "red" }}>{error}</p>}

      <button
        onClick={handleSave}
        disabled={saving}
        style={{ padding: "12px 32px", background: "#0066CC", color: "white", border: "none", borderRadius: 6, cursor: "pointer" }}
      >
        {saving ? "Saving..." : "Save Template"}
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Update App.tsx**

```tsx
import AdminTemplatePage from "./pages/AdminTemplatePage";

// In Routes:
<Route path="/admin/template" element={<AdminTemplatePage />} />
```

- [ ] **Step 3: Verify build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add frontend/src/
git commit -m "feat: add admin template registration page"
```

---

## Task 17: Copy gslides_builder.py Vendor & Final Integration

**Files:**
- Create: `backend/vendor/gslides_builder.py` (copy from plugin)
- Create: `backend/services/__init__.py`

- [ ] **Step 1: Vendor gslides_builder.py**

```bash
mkdir -p backend/vendor
cp ~/.vibe/marketplace/plugins/fe-google-tools/skills/google-slides/resources/gslides_builder.py backend/vendor/
touch backend/vendor/__init__.py
```

- [ ] **Step 2: Install Playwright browsers**

```bash
cd backend && uv run playwright install chromium
```

- [ ] **Step 3: Verify full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Verify frontend build + backend startup**

```bash
cd frontend && npm install && npm run build
cd ../backend && python -c "from main import app; print('Backend OK')"
```

- [ ] **Step 5: Commit**

```bash
git add backend/vendor/ backend/services/__init__.py
git commit -m "feat: vendor gslides_builder.py and finalize integration"
```

---

## Summary

| Task | Component | Description |
|------|-----------|-------------|
| 1 | Scaffolding | app.yaml, FastAPI, React + Vite setup |
| 2 | Models | Pydantic models for templates, widgets, generation |
| 3 | Template Service | CRUD with in-memory and Unity Catalog storage |
| 4 | Template API | REST endpoints for template management |
| 5 | Dashboard Service | Lakeview API client + widget parsing |
| 6 | Dashboard API | REST endpoints for dashboard listing |
| 7 | Capture Service | Playwright widget screenshot |
| 8 | LLM Service | Foundation Model API prompt + response parsing |
| 9 | Google Auth | OAuth flow for Google Slides access |
| 10 | Slides Service | gslides_builder.py wrapper with token injection |
| 11 | Generation API | End-to-end orchestrator endpoint |
| 12 | Frontend Types | TypeScript types + API client |
| 13 | Home Page | Template selection grid |
| 14 | Dashboard Page | Dashboard browser with search |
| 15 | Generate Page | Settings + progress + result |
| 16 | Admin Page | Template registration form |
| 17 | Integration | Vendor gslides_builder, final wiring |
