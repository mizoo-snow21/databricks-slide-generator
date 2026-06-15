"""Tests for TemplateService (in-memory store and UC sql_client path)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest

from models import (
    DesignTokens,
    Template,
    TemplateBrand,
    TemplateCreate,
    TemplateGuidelines,
)
from services.template_service import TemplateService


@pytest.fixture
def sample_create() -> TemplateCreate:
    return TemplateCreate(
        name="Corp Deck",
        google_slides_template_id="gslides-template-abc",
    )


class FakeSqlClient:
    """Records execute(sql, params) and returns scripted results."""

    def __init__(
        self,
        *,
        select_responses: list[list[dict[str, Any]]] | None = None,
        delete_rowcount: int = 1,
    ) -> None:
        self.calls: list[tuple[str, dict[str, Any] | None]] = []
        self._select_queue = list(select_responses or [])
        self.delete_rowcount = delete_rowcount

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> Any:
        self.calls.append((sql, params))
        head = sql.strip().upper()
        if head.startswith("INSERT"):
            return 1
        if head.startswith("UPDATE"):
            return 1
        if head.startswith("DELETE"):
            return self.delete_rowcount
        if head.startswith("SELECT"):
            if self._select_queue:
                return self._select_queue.pop(0)
            return []
        raise AssertionError(f"Unexpected SQL in fake client: {sql!r}")


def test_create_and_get(sample_create: TemplateCreate) -> None:
    svc = TemplateService(use_memory=True)
    created = svc.create(sample_create, user_id="user-1")

    assert created.id
    assert created.name == sample_create.name
    assert created.google_slides_template_id == sample_create.google_slides_template_id
    assert created.created_by == "user-1"
    assert created.created_at is not None
    assert created.updated_at is not None
    assert created.created_at == created.updated_at

    fetched = svc.get(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.model_dump() == created.model_dump()


def test_list_templates(sample_create: TemplateCreate) -> None:
    svc = TemplateService(use_memory=True)
    assert svc.list_all() == []

    t1 = svc.create(sample_create, user_id="u1")
    t2 = svc.create(
        TemplateCreate(name="Other", google_slides_template_id="gslides-other"),
        user_id="u2",
    )

    items = svc.list_all()
    assert len(items) == 2
    assert {t.id for t in items} == {t1.id, t2.id}


def test_delete(sample_create: TemplateCreate) -> None:
    svc = TemplateService(use_memory=True)
    created = svc.create(sample_create, user_id="user-1")

    svc.delete(created.id)
    svc.delete(created.id)

    assert svc.get(created.id) is None
    assert svc.list_all() == []


def test_delete_missing_id_is_noop(sample_create: TemplateCreate) -> None:
    svc = TemplateService(use_memory=True)
    created = svc.create(sample_create, user_id="u1")
    svc.delete("00000000-0000-0000-0000-000000000099")
    assert svc.get(created.id) is not None
    assert len(svc.list_all()) == 1


def test_get_nonexistent_returns_none() -> None:
    svc = TemplateService(use_memory=True)
    assert svc.get("00000000-0000-0000-0000-000000000000") is None


def test_update_memory_merges_pptx_file_path(sample_create: TemplateCreate) -> None:
    svc = TemplateService(use_memory=True)
    created = svc.create(sample_create, user_id="u1")
    path = "/tmp/template-example.pptx"
    updated = svc.update(created.id, {"pptx_file_path": path})
    assert updated is not None
    assert updated.pptx_file_path == path
    again = svc.get(created.id)
    assert again is not None
    assert again.pptx_file_path == path


def test_update_missing_template_returns_none() -> None:
    svc = TemplateService(use_memory=True)
    assert (
        svc.update("00000000-0000-0000-0000-000000000000", {"pptx_file_path": "x"})
        is None
    )


def test_insert_to_uc_calls_execute_with_params() -> None:
    fake = FakeSqlClient()
    svc = TemplateService(use_memory=False, sql_client=fake)
    now = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    tokens = DesignTokens(
        palette={"bg": "#000", "text": "#fff", "accent": "#f00", "muted": "#888"},
        fonts={"display": "Inter", "body": "Inter"},
        typeScale={"hero": 200, "title": 88, "body": 36, "caption": 24},
        spacing={"padding": 120, "gap": 48},
        radius=0,
    )
    template = Template(
        id="tid-1",
        name="N",
        description="D",
        google_slides_template_id="gslides-x",
        theme="dark",
        brand=TemplateBrand(primary="#111111"),
        guidelines=TemplateGuidelines(chart_preference="auto"),
        tokens=tokens,
        theme_markdown="Theme notes.",
        thumbnail_url=None,
        created_by="user-z",
        created_at=now,
        updated_at=now,
    )

    svc._insert_to_uc(template)

    assert len(fake.calls) == 1
    sql, params = fake.calls[0]
    assert "INSERT INTO" in sql
    assert ":id" in sql
    assert ":name" in sql
    assert ":tokens" in sql
    assert ":pptx_file_path" in sql
    assert ":theme_markdown" in sql
    assert "CAST(:created_at AS TIMESTAMP)" in sql
    assert "CAST(:updated_at AS TIMESTAMP)" in sql
    assert params is not None
    assert params["id"] == "tid-1"
    assert params["name"] == "N"
    assert params["description"] == "D"
    assert params["google_slides_template_id"] == "gslides-x"
    assert params["theme"] == "dark"
    assert json.loads(params["brand"]) == template.brand.model_dump()
    assert json.loads(params["guidelines"]) == template.guidelines.model_dump()
    assert json.loads(params["tokens"]) == tokens.model_dump()
    assert params["pptx_file_path"] is None
    assert params["theme_markdown"] == "Theme notes."
    assert params["thumbnail_url"] is None
    assert params["created_by"] == "user-z"


def test_insert_to_uc_serializes_none_tokens_as_null_params() -> None:
    fake = FakeSqlClient()
    svc = TemplateService(use_memory=False, sql_client=fake)
    now = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    template = Template(
        id="tid-null-tokens",
        name="N",
        description="D",
        google_slides_template_id="gslides-x",
        theme="dark",
        brand=TemplateBrand(primary="#111111"),
        guidelines=TemplateGuidelines(chart_preference="auto"),
        tokens=None,
        theme_markdown="",
        thumbnail_url=None,
        created_by="user-z",
        created_at=now,
        updated_at=now,
    )

    svc._insert_to_uc(template)

    sql, params = fake.calls[0]
    assert ":tokens" in sql
    assert params is not None
    assert params["tokens"] is None
    assert params["pptx_file_path"] is None
    assert params["theme_markdown"] == ""


def test_update_to_uc_sets_expected_columns() -> None:
    fake = FakeSqlClient()
    svc = TemplateService(use_memory=False, sql_client=fake)
    now = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    template = Template(
        id="tid-up",
        name="N",
        description="D",
        google_slides_template_id="gslides-x",
        theme="light",
        brand=TemplateBrand(primary="#111111"),
        guidelines=TemplateGuidelines(chart_preference="auto"),
        tokens=None,
        theme_markdown="tm",
        pptx_file_path="/abs/uploaded.pptx",
        thumbnail_url=None,
        created_by="user-z",
        created_at=now,
        updated_at=now,
    )
    svc._update_to_uc(template)
    sql, params = fake.calls[0]
    assert sql.strip().upper().startswith("UPDATE")
    assert ":pptx_file_path" in sql
    assert "CAST(:updated_at AS TIMESTAMP)" in sql
    assert params is not None
    assert params["pptx_file_path"] == "/abs/uploaded.pptx"
    assert params["id"] == "tid-up"


def test_fetch_from_uc_returns_template_from_row() -> None:
    created = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    brand = TemplateBrand(primary="#aaaaaa")
    guidelines = TemplateGuidelines(chart_preference="line_first")
    row = {
        "id": "r1",
        "name": "Row Name",
        "description": "Row Desc",
        "google_slides_template_id": "gslides-r1",
        "theme": "light",
        "brand": json.dumps(brand.model_dump()),
        "guidelines": json.dumps(guidelines.model_dump()),
        "tokens": None,
        "theme_markdown": "",
        "pptx_file_path": None,
        "thumbnail_url": None,
        "created_by": "creator",
        "created_at": created.isoformat(),
        "updated_at": created.isoformat(),
    }
    fake = FakeSqlClient(select_responses=[[row]])
    svc = TemplateService(use_memory=False, sql_client=fake)

    result = svc._fetch_from_uc("r1")

    assert len(fake.calls) == 1
    sql, params = fake.calls[0]
    assert "WHERE id = :id" in sql
    assert params == {"id": "r1"}
    assert result is not None
    assert result.id == "r1"
    assert result.name == "Row Name"
    assert result.brand.primary == "#aaaaaa"
    assert result.guidelines.chart_preference == "line_first"
    assert result.created_at == created


def test_list_from_uc_returns_templates_and_limit() -> None:
    row = {
        "id": "a",
        "name": "A",
        "description": "",
        "google_slides_template_id": "g",
        "theme": "light",
        "brand": json.dumps(TemplateBrand().model_dump()),
        "guidelines": json.dumps(
            TemplateGuidelines(chart_preference="auto").model_dump()
        ),
        "tokens": None,
        "theme_markdown": "",
        "pptx_file_path": None,
        "thumbnail_url": None,
        "created_by": "u",
        "created_at": "2024-01-01T00:00:00+00:00",
        "updated_at": "2024-01-01T00:00:00+00:00",
    }
    fake = FakeSqlClient(select_responses=[[row, {**row, "id": "b", "name": "B"}]])
    svc = TemplateService(use_memory=False, sql_client=fake)

    items = svc._list_from_uc()

    assert len(fake.calls) == 1
    sql, params = fake.calls[0]
    assert "ORDER BY created_at" in sql
    assert "LIMIT 1000" in sql
    assert params is None
    assert len(items) == 2
    assert {t.id for t in items} == {"a", "b"}


def test_delete_from_uc_uses_params_and_rowcount() -> None:
    fake = FakeSqlClient(delete_rowcount=1)
    svc = TemplateService(use_memory=False, sql_client=fake)
    assert svc._delete_from_uc("to-drop") is True
    sql, params = fake.calls[0]
    assert "DELETE FROM" in sql
    assert "WHERE id = :id" in sql
    assert params == {"id": "to-drop"}

    fake2 = FakeSqlClient(delete_rowcount=0)
    svc2 = TemplateService(use_memory=False, sql_client=fake2)
    assert svc2._delete_from_uc("missing") is False


def test_create_and_delete_uc_public_api(sample_create: TemplateCreate) -> None:
    fake = FakeSqlClient(delete_rowcount=1)
    svc = TemplateService(use_memory=False, sql_client=fake)
    created = svc.create(sample_create, user_id="uc-user")
    assert created.name == sample_create.name
    assert len(fake.calls) == 1
    insert_sql, insert_params = fake.calls[0]
    assert insert_sql.strip().upper().startswith("INSERT")
    assert insert_params is not None
    assert insert_params["created_by"] == "uc-user"

    svc.delete(created.id)
    delete_sql, delete_params = fake.calls[1]
    assert delete_sql.strip().upper().startswith("DELETE")
    assert delete_params == {"id": created.id}


def test_get_uc_passes_id_as_parameter_not_string_concat() -> None:
    malicious_id = "x' OR '1'='1"
    fake = FakeSqlClient(select_responses=[[]])
    svc = TemplateService(use_memory=False, sql_client=fake)
    assert svc.get(malicious_id) is None
    _sql, params = fake.calls[0]
    assert params == {"id": malicious_id}


def test_coerce_datetime_none_and_iso_str_and_aware() -> None:
    svc = TemplateService(use_memory=True)
    assert svc._coerce_datetime(None) is None
    dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert svc._coerce_datetime(dt) == dt
    assert svc._coerce_datetime("2024-01-01T00:00:00+00:00") == dt
    naive = datetime(2024, 1, 1, 0, 0, 0)
    coerced = svc._coerce_datetime(naive)
    assert coerced == naive.replace(tzinfo=timezone.utc)


def test_coerce_datetime_rejects_unsupported_type() -> None:
    svc = TemplateService(use_memory=True)
    with pytest.raises(TypeError, match="Unsupported datetime value type"):
        svc._coerce_datetime(12345)


def test_parse_brand_and_guidelines() -> None:
    svc = TemplateService(use_memory=True)
    b = TemplateBrand(accent="#ff0000")
    g = TemplateGuidelines(chart_preference="pie_first")
    assert svc._parse_brand(json.dumps(b.model_dump())).accent == "#ff0000"
    assert svc._parse_brand(b.model_dump()).accent == "#ff0000"
    assert (
        svc._parse_guidelines(json.dumps(g.model_dump())).chart_preference
        == "pie_first"
    )
    assert svc._parse_guidelines(g.model_dump()).chart_preference == "pie_first"


def test_parse_brand_invalid_type() -> None:
    svc = TemplateService(use_memory=True)
    with pytest.raises(TypeError, match="Invalid brand column type"):
        svc._parse_brand(42)


def test_parse_guidelines_invalid_type() -> None:
    svc = TemplateService(use_memory=True)
    with pytest.raises(TypeError, match="Invalid guidelines column type"):
        svc._parse_guidelines(["not", "a", "guideline"])


def test_create_template_persists_tokens_and_theme_markdown() -> None:
    svc = TemplateService(use_memory=True)
    created = svc.create(
        TemplateCreate(
            name="Test",
            google_slides_template_id="abc",
            tokens=DesignTokens(
                palette={
                    "bg": "#000",
                    "text": "#fff",
                    "accent": "#f00",
                    "muted": "#888",
                },
                fonts={"display": "Inter", "body": "Inter"},
                typeScale={
                    "hero": 200,
                    "title": 88,
                    "body": 36,
                    "caption": 24,
                },
                spacing={"padding": 120, "gap": 48},
                radius=0,
            ),
            theme_markdown="Mono editorial.",
        ),
        user_id="u1",
    )

    fetched = svc.get(created.id)
    assert fetched is not None
    assert fetched.tokens is not None
    assert fetched.tokens.palette["accent"] == "#f00"
    assert fetched.theme_markdown == "Mono editorial."


def test_fetch_from_uc_parses_tokens_json_string() -> None:
    tokens = DesignTokens(
        palette={"bg": "#000", "text": "#fff", "accent": "#abc", "muted": "#888"},
        fonts={"display": "Inter", "body": "Inter"},
        typeScale={"hero": 100, "title": 88, "body": 36, "caption": 24},
        spacing={"padding": 120, "gap": 48},
        radius=2,
    )
    brand = TemplateBrand(primary="#aaa")
    guidelines = TemplateGuidelines(chart_preference="auto")
    created = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    row = {
        "id": "tk",
        "name": "T",
        "description": "",
        "google_slides_template_id": "g",
        "theme": "light",
        "brand": json.dumps(brand.model_dump()),
        "guidelines": json.dumps(guidelines.model_dump()),
        "tokens": json.dumps(tokens.model_dump()),
        "theme_markdown": "From UC.",
        "pptx_file_path": None,
        "thumbnail_url": None,
        "created_by": "u",
        "created_at": created.isoformat(),
        "updated_at": created.isoformat(),
    }
    fake = FakeSqlClient(select_responses=[[row]])
    svc_sql = TemplateService(use_memory=False, sql_client=fake)

    fetched = svc_sql._fetch_from_uc("tk")

    assert fetched is not None
    assert fetched.tokens is not None
    assert fetched.tokens.radius == 2
    assert fetched.tokens.palette["accent"] == "#abc"
    assert fetched.theme_markdown == "From UC."
