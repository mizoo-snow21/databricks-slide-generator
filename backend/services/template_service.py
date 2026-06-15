from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from config import get_settings
from models import (
    DesignTokens,
    Template,
    TemplateBrand,
    TemplateCreate,
    TemplateGuidelines,
)


_UC_SELECT_COLUMNS = (
    "id",
    "name",
    "description",
    "google_slides_template_id",
    "theme",
    "brand",
    "guidelines",
    "tokens",
    "theme_markdown",
    "pptx_file_path",
    "thumbnail_url",
    "created_by",
    "created_at",
    "updated_at",
)

_UC_LIST_LIMIT = 1000


class TemplateService:
    """CRUD for slide templates: in-memory dict or Unity Catalog table."""

    def __init__(
        self,
        use_memory: bool = False,
        sql_client: Any = None,
        persist_path: str | None = None,
    ) -> None:
        self._use_memory = use_memory
        self._sql_client = sql_client
        self._memory: dict[str, Template] = {}
        self._catalog: str = ""
        self._schema: str = ""
        self._persist_path = persist_path if use_memory else None
        if not use_memory:
            settings = get_settings()
            self._catalog = settings.uc_catalog
            self._schema = settings.uc_schema
        if self._persist_path:
            self._load()

    def _load(self) -> None:
        import os as _os

        path = self._persist_path
        if not path or not _os.path.exists(path):
            return
        try:
            with open(path, "r") as f:
                data = json.load(f)
            for raw in data:
                t = Template.model_validate(raw)
                self._memory[t.id] = t
        except Exception:
            pass

    def _save(self) -> None:
        import os as _os

        path = self._persist_path
        if not path:
            return
        _os.makedirs(_os.path.dirname(path) or ".", exist_ok=True)
        payload = [t.model_dump(mode="json") for t in self._memory.values()]
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(payload, f)
        _os.replace(tmp, path)

    @staticmethod
    def _sanitize(value: str) -> str:
        return value.replace("'", "''")

    def _table_ident(self) -> str:
        return f"`{self._catalog}`.`{self._schema}`.`templates`"

    def create(self, data: TemplateCreate, user_id: str) -> Template:
        now = datetime.now(timezone.utc)
        template_id = str(uuid.uuid4())
        template = Template(
            **data.model_dump(exclude={"pptx_upload_id"}),
            id=template_id,
            created_by=user_id,
            created_at=now,
            updated_at=now,
        )
        if self._use_memory:
            self._memory[template_id] = template
            self._save()
        else:
            self._insert_to_uc(template)
        return template

    def update(self, template_id: str, patch: dict[str, Any]) -> Optional[Template]:
        existing = self.get(template_id)
        if existing is None:
            return None
        now = datetime.now(timezone.utc)
        allowed = set(Template.model_fields.keys())
        clean = {k: v for k, v in patch.items() if k in allowed}
        updated = existing.model_copy(update={**clean, "updated_at": now})
        if self._use_memory:
            self._memory[template_id] = updated
            self._save()
        else:
            self._update_to_uc(updated)
        return updated

    def get(self, template_id: str) -> Optional[Template]:
        if self._use_memory:
            return self._memory.get(template_id)
        return self._fetch_from_uc(template_id)

    def list_all(self) -> List[Template]:
        if self._use_memory:
            return list(self._memory.values())
        return self._list_from_uc()

    def delete(self, template_id: str) -> bool:
        if self._use_memory:
            removed = self._memory.pop(template_id, None) is not None
            if removed:
                self._save()
            return removed
        return self._delete_from_uc(template_id)

    def _require_sql_client(self) -> Any:
        if self._sql_client is None:
            msg = "sql_client is required when use_memory is False"
            raise RuntimeError(msg)
        return self._sql_client

    def _sql_execute(self, sql: str, params: dict[str, Any] | None = None) -> Any:
        client = self._require_sql_client()
        if params is None:
            return client.execute(sql)
        return client.execute(sql, params)

    @staticmethod
    def _dml_rowcount(result: Any) -> int:
        if result is None:
            return 0
        if type(result) is int:
            return result
        if isinstance(result, dict) and "rowcount" in result:
            return int(result["rowcount"])
        msg = (
            "sql_client.execute for DML must return int rowcount, "
            "dict with 'rowcount', or None"
        )
        raise TypeError(msg)

    def _row_as_dict(self, row: Any) -> dict[str, Any]:
        if isinstance(row, dict):
            return {str(k).lower(): v for k, v in row.items()}
        if isinstance(row, (list, tuple)):
            return {
                _UC_SELECT_COLUMNS[i]: row[i]
                for i in range(min(len(row), len(_UC_SELECT_COLUMNS)))
            }
        msg = f"Unsupported row type: {type(row)}"
        raise TypeError(msg)

    def _rows_from_result(self, raw: Any) -> list[dict[str, Any]]:
        if raw is None:
            return []
        if not isinstance(raw, list):
            msg = "sql_client.execute must return a list of rows or None for queries"
            raise TypeError(msg)
        return [self._row_as_dict(r) for r in raw]

    def _coerce_datetime(self, value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value
        if isinstance(value, str):
            normalized = value.replace("Z", "+00:00")
            return datetime.fromisoformat(normalized)
        msg = f"Unsupported datetime value type: {type(value)}"
        raise TypeError(msg)

    def _parse_brand(self, raw: Any) -> TemplateBrand:
        if isinstance(raw, str):
            return TemplateBrand.model_validate(json.loads(raw))
        if isinstance(raw, dict):
            return TemplateBrand.model_validate(raw)
        msg = f"Invalid brand column type: {type(raw)}"
        raise TypeError(msg)

    def _parse_guidelines(self, raw: Any) -> TemplateGuidelines:
        if isinstance(raw, str):
            return TemplateGuidelines.model_validate(json.loads(raw))
        if isinstance(raw, dict):
            return TemplateGuidelines.model_validate(raw)
        msg = f"Invalid guidelines column type: {type(raw)}"
        raise TypeError(msg)

    def _parse_tokens(self, raw: Any) -> Optional[DesignTokens]:
        if raw is None:
            return None
        if isinstance(raw, str):
            stripped = raw.strip()
            if not stripped or stripped.lower() == "null":
                return None
            return DesignTokens.model_validate(json.loads(stripped))
        if isinstance(raw, dict):
            return DesignTokens.model_validate(raw)
        msg = f"Invalid tokens column type: {type(raw)}"
        raise TypeError(msg)

    def _template_from_uc_row(self, row: dict[str, Any]) -> Template:
        created_at = self._coerce_datetime(row.get("created_at"))
        updated_at = self._coerce_datetime(row.get("updated_at"))
        return Template(
            id=str(row["id"]),
            name=str(row["name"]),
            description=str(row.get("description") or ""),
            google_slides_template_id=str(row["google_slides_template_id"]),
            theme=str(row.get("theme") or "light"),
            brand=self._parse_brand(row["brand"]),
            guidelines=self._parse_guidelines(row["guidelines"]),
            tokens=self._parse_tokens(row.get("tokens")),
            theme_markdown=str(row.get("theme_markdown") or ""),
            pptx_file_path=row.get("pptx_file_path"),
            thumbnail_url=row.get("thumbnail_url"),
            created_by=str(row.get("created_by") or ""),
            created_at=created_at,
            updated_at=updated_at,
        )

    def _insert_to_uc(self, template: Template) -> None:
        brand_json = json.dumps(template.brand.model_dump())
        guidelines_json = json.dumps(template.guidelines.model_dump())
        tokens_json = (
            json.dumps(template.tokens.model_dump()) if template.tokens else None
        )
        created_at = template.created_at or datetime.now(timezone.utc)
        updated_at = template.updated_at or created_at
        cols = ", ".join(_UC_SELECT_COLUMNS)
        placeholders = ", ".join(
            f"CAST(:{c} AS TIMESTAMP)" if c in ("created_at", "updated_at") else f":{c}"
            for c in _UC_SELECT_COLUMNS
        )
        sql = f"INSERT INTO {self._table_ident()} ({cols}) VALUES ({placeholders})"
        params = {
            "id": template.id,
            "name": template.name,
            "description": template.description,
            "google_slides_template_id": template.google_slides_template_id,
            "theme": template.theme,
            "brand": brand_json,
            "guidelines": guidelines_json,
            "tokens": tokens_json,
            "theme_markdown": template.theme_markdown or "",
            "pptx_file_path": template.pptx_file_path,
            "thumbnail_url": template.thumbnail_url,
            "created_by": template.created_by,
            "created_at": created_at.isoformat(),
            "updated_at": updated_at.isoformat(),
        }
        self._sql_execute(sql, params)

    def _update_to_uc(self, template: Template) -> None:
        brand_json = json.dumps(template.brand.model_dump())
        guidelines_json = json.dumps(template.guidelines.model_dump())
        tokens_json = (
            json.dumps(template.tokens.model_dump()) if template.tokens else None
        )
        updated_at = template.updated_at or datetime.now(timezone.utc)
        assignments = ", ".join(
            f"{c} = CAST(:{c} AS TIMESTAMP)" if c == "updated_at" else f"{c} = :{c}"
            for c in _UC_SELECT_COLUMNS
            if c not in ("id", "created_at", "created_by")
        )
        sql = f"UPDATE {self._table_ident()} SET {assignments} WHERE id = :id"
        params = {
            "id": template.id,
            "name": template.name,
            "description": template.description,
            "google_slides_template_id": template.google_slides_template_id,
            "theme": template.theme,
            "brand": brand_json,
            "guidelines": guidelines_json,
            "tokens": tokens_json,
            "theme_markdown": template.theme_markdown or "",
            "pptx_file_path": template.pptx_file_path,
            "thumbnail_url": template.thumbnail_url,
            "updated_at": updated_at.isoformat(),
        }
        self._sql_execute(sql, params)

    def _fetch_from_uc(self, template_id: str) -> Optional[Template]:
        col_list = ", ".join(_UC_SELECT_COLUMNS)
        sql = f"SELECT {col_list} FROM {self._table_ident()} WHERE id = :id LIMIT 1"
        rows = self._rows_from_result(self._sql_execute(sql, {"id": template_id}))
        if not rows:
            return None
        return self._template_from_uc_row(rows[0])

    def _list_from_uc(self) -> List[Template]:
        col_list = ", ".join(_UC_SELECT_COLUMNS)
        sql = (
            f"SELECT {col_list} FROM {self._table_ident()} "
            f"ORDER BY created_at LIMIT {_UC_LIST_LIMIT}"
        )
        rows = self._rows_from_result(self._sql_execute(sql))
        return [self._template_from_uc_row(r) for r in rows]

    def _delete_from_uc(self, template_id: str) -> bool:
        sql = f"DELETE FROM {self._table_ident()} WHERE id = :id"
        result = self._sql_execute(sql, {"id": template_id})
        return self._dml_rowcount(result) > 0
