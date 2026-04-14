# Genie Slide - Design Spec

## Overview

Databricks App that automatically generates Google Slides presentations from AI/BI Lakeview Dashboards. Administrators register slide templates with style guidelines, and customer business users select a template and dashboard to generate a presentation with one click. An LLM analyzes the dashboard content, maps widgets to appropriate slide layouts, generates narrative text, and outputs a complete Google Slides deck.

## Target Users

- **Primary**: Customer business users who create slides from dashboards (QBR, monthly reports, exec reviews)
- **Secondary**: Administrators who register and manage slide templates

## Core User Flow

```
1. Select template    → Admin-registered templates with brand/style guidelines
2. Select dashboard   → Lakeview Dashboards from the user's workspace
3. (Optional) Prompt  → "エグゼクティブ向けに簡潔に。NA地域にフォーカス"
4. Generate           → One click → Google Slides URL (30s-1min)
```

## Architecture

```
┌─────────────────────────────────────────────┐
│           Databricks App (React + FastAPI)   │
│                                             │
│  Frontend (React + TypeScript)              │
│  ├── Template list / selection              │
│  ├── Dashboard browser / selection          │
│  ├── Prompt input                           │
│  ├── Generation progress + result           │
│  └── Admin: Template registration           │
│                                             │
│  Backend (Python + FastAPI)                 │
│  ├── Dashboard API client                   │
│  ├── Playwright chart capture               │
│  ├── LLM orchestration (Foundation Model)   │
│  ├── Google Slides generation               │
│  └── Template CRUD                          │
└─────────────────────────────────────────────┘
```

## Key Design Decisions

### 1. Template = Style Guide (not rigid slots)

Templates define guidelines, not fixed slot structures. The LLM has access to the full set of `gslides_builder.py` layouts and freely chooses the best combination based on the dashboard content and user prompt.

**Template definition:**

```json
{
  "id": "qbr-standard",
  "name": "Quarterly Business Review",
  "description": "Standard QBR template (6-10 slides)",
  "thumbnail_url": "...",
  "theme": "light",
  "google_slides_template_id": "<customer's Google Slides template ID>",
  "brand": {
    "primary": "#1A73E8",
    "secondary": "#34A853",
    "accent": "#EA4335",
    "text_dark": "#202124",
    "text_light": "#FFFFFF",
    "font": "Noto Sans JP"
  },
  "guidelines": {
    "total_slides": { "min": 6, "max": 12 },
    "structure_hint": "Overview → Data detail → Insights → Next actions",
    "preferred_layouts": ["title", "content_basic", "content_2col", "title_only", "closing"],
    "style_notes": "Executive audience. Concise. One message per slide.",
    "must_include": ["title", "closing"],
    "chart_preference": "Use title_only with table for data-heavy slides"
  }
}
```

**Why this approach:**
- Rigid slot systems break when the dashboard doesn't match the expected structure
- The LLM can adapt to any dashboard's widget composition
- Different templates change tone/structure without code changes
- Proven by Genie Slides (LLM selects layouts) and Account Review Deck (LLM generates create-from-spec JSON)

### 2. Chart Capture via Playwright (not matplotlib recreation)

Dashboard widgets are captured as high-quality PNG screenshots using Playwright, following the approach proven by the AI/BI Google Slides Export Wizard.

**Why this approach:**
- Preserves exact dashboard appearance (colors, fonts, layout)
- No re-creation artifacts from matplotlib
- Automatically supports all chart types (current and future)
- Proven by AI/BI Google Slides Export Wizard (Confluence: 5144937309)

**Chart color priority:**
1. Dashboard's own visualization settings → use as-is (captured via screenshot)
2. Template brand colors → applied to LLM-generated text/styling
3. Neutral palette → fallback

### 3. LLM Handles All Creative Decisions

A single LLM call handles mapping, text generation, and narrative structure.

**Input to LLM:**
- Template guidelines JSON
- Available layouts reference (from gslides_builder.py)
- Dashboard widget list (title, viz type, query result summary, columns, row count)
- User prompt (optional)

**Output from LLM:**
- `create-from-spec` compatible JSON array
- Each slide specifies layout, text content, and which widget_id to embed
- Ready to pass directly to `gslides_builder.py`

**LLM responsibilities:**
1. **Mapping**: Which widgets go on which slides
2. **Text generation**: Slide titles, bullet points, insights, commentary
3. **Narrative structure**: Story arc across slides (overview → detail → insight → action)

**Example LLM output:**

```json
[
  {"layout": "title", "title": "Q4 Business Review", "subtitle": "+15% Revenue Growth — Led by NA Region"},
  {"layout": "section_break_1", "title": "Performance Overview"},
  {"layout": "content_basic", "title": "Key KPIs", "body": "Total Revenue: $12.3M (+15%)\nMAU: 1,234 (+8%)\nCost Efficiency: 92%", "bullets": true},
  {"layout": "title_only", "title": "Revenue Trend: NA Region Drives Growth", "_widget_id": "w_abc123"},
  {"layout": "content_2col", "title": "Regional Comparison", "_left_widget_id": "w_def456", "_right_widget_id": "w_ghi789", "columns": ["NA Region", "YoY +22%, strong momentum", "APAC", "YoY +8%, stable growth"]},
  {"layout": "content_basic", "title": "Next Actions", "body": "1. Strengthen APAC campaigns\n2. Continue cost optimization\n3. Evaluate new SKU expansion", "bullets": true},
  {"layout": "closing"}
]
```

### 4. No Databricks Branding Dependency

The system is brand-agnostic:
- No hardcoded Databricks corporate template
- Admins register their own Google Slides template (any template)
- Brand colors are defined per template
- Charts are screenshots from the customer's own dashboard (inherits their styling)

### 5. Security & Tenant Isolation

All operations run under the requesting user's identity. No cross-user data access is possible.

**Databricks identity & dashboard access:**
- The Databricks App runs with the authenticated user's token (Databricks App OAuth, automatic)
- Dashboard API calls use the user's token — they can only list/read dashboards they have permission to view
- SQL Statements API executes queries as the user — row-level security (RLS) and column-level security apply exactly as they do in the dashboard itself
- Playwright opens the published dashboard URL authenticated as the user — the rendered content respects the same permissions

**Google credentials & deck ownership:**
- Google OAuth tokens are stored in the user's browser session only (httpOnly cookie or session storage) — never persisted server-side or in Unity Catalog
- Generated Google Slides decks are owned by the user's Google account — the app never retains write access after generation
- The backend holds the Google token only for the duration of the generation request; it is discarded after the response is returned

**Admin boundary:**
- Template registration requires an admin role (checked via Databricks group membership)
- Templates contain no sensitive data (only style guidelines and a Google Slides template ID) — any user can read templates, only admins can write
- Template `google_slides_template_id` is validated on registration: the backend confirms the admin has read access to that Google Slides file

### 6. Error Handling & Fallback Strategy

The generation pipeline must handle partial failures gracefully rather than failing the entire request.

**Widget capture failures:**

| Failure | Behavior |
|---------|----------|
| Widget fails to render within 15s | Skip widget, mark as `capture_failed` in widget list |
| Unsupported widget type (e.g., custom viz, map) | Skip widget, mark as `unsupported` |
| Entire dashboard fails to load within 30s | Abort generation, return error with message "Dashboard could not be loaded. Verify the dashboard is published and accessible." |
| Playwright crash | Retry once; if second attempt fails, abort with infrastructure error |

**SQL query failures:**

| Failure | Behavior |
|---------|----------|
| Query timeout (>30s) | Skip query result summary for that widget; LLM receives widget metadata only (title, viz type) without data summary |
| Query permission error | Skip widget entirely; log warning |
| All queries fail | Proceed with widget metadata only — LLM generates slides based on widget titles/types without data-driven insights, and the generated deck includes a note that data summaries were unavailable |

**RLS considerations:**
- Queries execute as the requesting user — results reflect their RLS permissions
- If a user has restricted access, the LLM receives only the data they are authorized to see
- No special handling needed: the system inherits the platform's access control

**LLM failure:**
- If the Foundation Model API returns an error or invalid JSON, retry once with the same input
- If second attempt fails, return error to user: "Slide composition failed. Please try again."

**Google Slides failure:**
- If Google API quota is exceeded or auth fails, return error with specific guidance ("Re-authenticate with Google" or "Try again in a few minutes")
- If template copy fails (template deleted or no access), return error: "The selected template is no longer accessible. Contact your administrator."

**Partial success:**
- If some widgets were skipped but the dashboard loaded and LLM succeeded, the generation completes
- The result screen shows a warning: "N widgets could not be captured and were excluded from the presentation"
- The LLM is informed which widgets were skipped so it can adjust the narrative accordingly

**Timeout budget (target: 30s-90s total):**

| Step | Budget | Notes |
|------|--------|-------|
| Dashboard API + SQL queries | 10s | Parallel execution, 30s per-query timeout |
| Playwright render + capture | 30s | 15s page load + 1-2s per widget |
| LLM composition | 15s | Single call |
| Google Slides generation | 20s | Template copy + create-from-spec + image upload |
| **Total** | **~75s worst case** | Frontend shows progress bar with step indicators |

### 7. Data Governance & Sensitive Data Handling

Dashboard data flows through the system temporarily during generation. All temporary artifacts must be cleaned up.

**Temporary artifacts:**

| Artifact | Contains | Lifetime | Cleanup |
|----------|----------|----------|---------|
| Widget PNG screenshots | Dashboard visualizations (may contain sensitive business data) | Duration of request only | Deleted from temp directory immediately after Google Drive upload completes |
| Query result summaries | Aggregated data sent to LLM (column names, row counts, statistical summaries — never raw row data) | Duration of request only | In-memory only, garbage collected after response |
| Google Drive uploaded PNGs | Same as widget PNGs | Slides reference them by URL | After inserting into slides, images are embedded; the Drive files are deleted within 60s of generation completion |
| LLM prompt/response | Template guidelines + widget summaries + generated JSON | Duration of request only | In-memory only, not logged beyond standard Foundation Model API audit logs |

**What is persisted (generation_history table):**
- Only metadata: template ID, dashboard ID, user ID, Google Slides URL, slide count, timestamp
- No query results, no widget images, no LLM prompts/responses, no data summaries
- Users can only query their own generation history (filtered by user_id = current user)

**Google Drive cleanup:**
- After `create-from-spec` inserts images into slides, the backend deletes the uploaded PNGs from Google Drive
- If deletion fails (e.g., network error), a background cleanup job retries deletion for up to 24 hours
- Drive files are created in a dedicated app-managed folder with no sharing permissions (only the generating user has access during the brief upload window)

**LLM data minimization:**
- The LLM receives widget summaries (e.g., "12 rows, columns: month/revenue/region, max revenue: $1.5M in Oct"), never raw query result rows
- User prompts are not stored beyond the request lifecycle
- Foundation Model API's own audit logging applies per Databricks platform policy

## Data Flow

### Step 1: Dashboard Data Retrieval

```
GET /api/2.0/lakeview/dashboards/{dashboard_id}/published
  → Dashboard definition (name, description, widgets, queries)

POST /api/2.0/sql/statements
  → Execute each widget's query → get actual data
  → Summarize results for LLM context (not full datasets)
```

### Step 2: Widget Image Capture

```
Playwright
  → Open published dashboard URL (authenticated)
  → Wait for all widgets to render
  → For each widget element: element.screenshot() → PNG
  → Save to temp directory
```

### Step 3: LLM Slide Composition

```
Foundation Model API
  → Input: template guidelines + widget summaries + user prompt
  → Output: create-from-spec JSON with widget_id references
```

### Step 4: Google Slides Generation

```
gslides_builder.py
  → Copy customer's Google Slides template
  → create-from-spec with the LLM-generated JSON
  → For slides with _widget_id references:
    → Upload PNG to Google Drive
    → Insert image into the corresponding slide
  → Return Google Slides URL
```

## Tech Stack

| Layer | Technology | Reason |
|-------|-----------|--------|
| Frontend | React + TypeScript | Databricks App standard |
| Backend | Python + FastAPI | Databricks App standard, gslides_builder.py compatibility |
| Package management | uv + pyproject.toml | Fast, lockfile-based Python dependency management |
| LLM | Foundation Model API | Stays within Databricks platform |
| Dashboard data | Lakeview Dashboard API + SQL Statements API | Widget definitions and query results |
| Chart capture | Playwright | Proven by Export Wizard |
| Slide generation | gslides_builder.py (create-from-spec) | Proven by Account Review Deck |
| Google auth | OAuth 2.0 (per user) | Google Slides write access |
| Template storage | Unity Catalog table | Within Databricks platform |
| Generation history | Unity Catalog table | Audit trail |

## Screens

### Screen 1: Home (Template Selection)

- Grid of registered templates with thumbnails
- Admin users see a "+ Register Template" button
- Each template shows: name, description, slide count range

### Screen 2: Dashboard Selection

- List of Lakeview Dashboards from the user's workspace
- Search/filter bar
- Shows: dashboard name, last updated, widget count

### Screen 3: Generation Settings

- Selected template and dashboard summary
- Optional text prompt field
- "Generate" button

### Screen 4: Result

- Google Slides URL (clickable)
- Slide thumbnails preview
- "Regenerate" and "Try another dashboard" buttons

### Admin Screen: Template Registration

- Template name, description
- Google Slides template ID (the customer's own template)
- Theme (light/dark)
- Brand colors (primary, secondary, accent, text dark, text light)
- Font family
- Guidelines: slide count range, structure hint, preferred layouts, style notes, must-include layouts, chart preference

## Storage Schema

### slide_templates

| Column | Type | Description |
|--------|------|-------------|
| id | STRING | Unique template ID |
| name | STRING | Display name |
| description | STRING | Template description |
| thumbnail_url | STRING | Preview image URL |
| google_slides_template_id | STRING | Google Slides template to copy |
| theme | STRING | "light" or "dark" |
| brand | STRING (JSON) | Brand colors and font |
| guidelines | STRING (JSON) | LLM guidelines |
| created_by | STRING | Admin user ID |
| created_at | TIMESTAMP | Creation time |
| updated_at | TIMESTAMP | Last update time |

### generation_history

| Column | Type | Description |
|--------|------|-------------|
| id | STRING | Generation ID |
| template_id | STRING | Template used |
| dashboard_id | STRING | Source dashboard |
| user_id | STRING | User who generated |
| user_prompt | STRING | Optional prompt |
| google_slides_url | STRING | Generated presentation URL |
| slide_count | INT | Number of slides generated |
| created_at | TIMESTAMP | Generation time |

## Prior Art & References

| Implementation | Approach | Relevance |
|---------------|----------|-----------|
| **AI/BI Google Slides Export Wizard** (Confluence 5144937309) | Widget screenshot → Google Slides | Chart capture method |
| **Account Review Deck** (fe-workflows skill) | LLM → create-from-spec JSON → gslides_builder.py | Slide generation pipeline |
| **Genie Slides** (Confluence 6114836646) | LLM tools (create_slide, create_slide_deck, edit_slide) | LLM-driven layout selection |
| **Genie Presentations** (Confluence 6121980271) | Dashboard Insight Genie → slides | Dashboard-to-slide concept |
| **Dashboard Subscriptions** (product feature) | PNG snapshot for Slack/Teams | Dashboard image export precedent |

## Scope & Non-Goals

### In Scope (Phase 1)
- Template CRUD (admin)
- Dashboard selection and widget capture
- LLM-based slide composition
- Google Slides generation with chart images
- Per-user Google OAuth
- Generation history

### Out of Scope (Future Phases)
- Genie API integration (ad-hoc analysis injection) — Phase 2
- Slide editing/refinement within the app — Phase 2
- PowerPoint export — Future
- Live data refresh in existing presentations — Future
- Scheduled/recurring generation — Future
- On-platform slide rendering (non-Google Slides) — Future
