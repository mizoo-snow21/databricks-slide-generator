"""Databricks Genie Spaces: list, describe, and ask (NL → SQL → result table)."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from pydantic import BaseModel, Field

from services.llm_service import LLMService

# Terminal message statuses — stop polling when status name matches one of these.
_TERMINAL_STATUSES = frozenset(
    {"COMPLETED", "FAILED", "CANCELLED", "QUERY_RESULT_EXPIRED"}
)


class GenieSpaceInfo(BaseModel):
    space_id: str
    title: str
    description: str = ""
    warehouse_id: str | None = None


class GenieAnswer(BaseModel):
    question: str
    sql: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    status: str  # "ok" | "failed"
    error: str | None = None


def _status_name(status: Any) -> str:
    return str(status).split(".")[-1]


def _state_name(state: Any) -> str | None:
    if state is None:
        return None
    return str(state).split(".")[-1]


def list_spaces(client: Any) -> list[GenieSpaceInfo]:
    """Return Genie spaces from the first page of list_spaces (pagination ignored)."""
    resp = client.genie.list_spaces()
    # Demo scope: first page only; ignore resp.next_page_token when present.
    return [
        GenieSpaceInfo(space_id=s.space_id, title=s.title, description="")
        for s in resp.spaces
    ]


def get_space(client: Any, space_id: str) -> GenieSpaceInfo:
    space = client.genie.get_space(space_id)
    description = getattr(space, "description", None) or ""
    return GenieSpaceInfo(
        space_id=space_id,
        title=space.title,
        description=description,
        warehouse_id=getattr(space, "warehouse_id", None),
    )


def _rows_from_result(res: Any) -> tuple[list[str], list[dict[str, Any]]]:
    stmt = res.statement_response
    columns = [c.name for c in stmt.manifest.schema.columns]
    data_array = stmt.result.data_array or []
    rows = [dict(zip(columns, row, strict=False)) for row in data_array]
    return columns, rows


def _failed_answer(question: str, error: str) -> GenieAnswer:
    return GenieAnswer(
        question=question,
        sql=None,
        columns=[],
        rows=[],
        status="failed",
        error=error,
    )


def _find_query_attachment(message: Any) -> Any | None:
    for attachment in getattr(message, "attachments", None) or []:
        if getattr(attachment, "query", None) is not None:
            return attachment
    return None


def _handle_completed(
    client: Any,
    space_id: str,
    conversation_id: str,
    message_id: str,
    question: str,
    message: Any,
) -> GenieAnswer:
    attachment = _find_query_attachment(message)
    if attachment is None:
        return _failed_answer(question, "Genie completed without a query attachment")

    sql = attachment.query.query
    attachment_id = attachment.attachment_id
    res = client.genie.get_message_query_result_by_attachment(
        space_id,
        conversation_id,
        message_id,
        attachment_id,
    )

    stmt = res.statement_response
    status_obj = getattr(stmt, "status", None)
    state_name = _state_name(getattr(status_obj, "state", None))
    if state_name != "SUCCEEDED":
        return _failed_answer(
            question,
            f"Query result state was {state_name or 'unknown'}",
        )

    if (
        stmt.manifest is None
        or stmt.manifest.schema is None
        or stmt.result is None
    ):
        return _failed_answer(
            question, "Genie returned no result manifest/result"
        )

    columns, rows = _rows_from_result(res)
    if columns == ["error_message"]:
        detail = rows[0].get("error_message", "unknown error") if rows else "unknown error"
        return _failed_answer(question, str(detail))

    return GenieAnswer(
        question=question,
        sql=sql,
        columns=columns,
        rows=rows,
        status="ok",
        error=None,
    )


def ask(
    client: Any,
    space_id: str,
    question: str,
    *,
    poll_interval_s: float = 3.0,
    max_polls: int = 60,
) -> GenieAnswer:
    """Ask Genie a question; poll until terminal status or max_polls exhausted."""
    try:
        wait = client.genie.start_conversation(space_id=space_id, content=question)
        response = wait.response
        conversation_id = response.conversation_id
        message_id = getattr(response, "message_id", None) or getattr(response, "id", None)

        for poll_idx in range(max_polls):
            message = client.genie.get_message(space_id, conversation_id, message_id)
            status_name = _status_name(message.status)

            if status_name in _TERMINAL_STATUSES:
                if status_name == "COMPLETED":
                    return _handle_completed(
                        client,
                        space_id,
                        conversation_id,
                        message_id,
                        question,
                        message,
                    )
                return _failed_answer(question, f"Genie status: {status_name}")

            if poll_idx < max_polls - 1:
                time.sleep(poll_interval_s)

        return _failed_answer(question, "timeout waiting for Genie response")
    except Exception as exc:
        return _failed_answer(question, f"Genie request failed: {exc}")


async def ask_many(
    client: Any,
    space_id: str,
    questions: list[str],
    *,
    max_polls: int = 60,
) -> tuple[list[GenieAnswer], list[str]]:
    """Ask multiple questions concurrently; return ok answers and failure warnings."""
    if not questions:
        return [], []

    answers = await asyncio.gather(
        *[
            asyncio.to_thread(ask, client, space_id, q, max_polls=max_polls)
            for q in questions
        ]
    )

    ok_answers: list[GenieAnswer] = []
    warnings: list[str] = []
    for answer in answers:
        if answer.status == "ok":
            ok_answers.append(answer)
        else:
            warnings.append(f"{answer.question}: {answer.error or 'unknown error'}")
    return ok_answers, warnings


def suggest_questions(
    llm: LLMService,
    space: GenieSpaceInfo,
    n: int = 8,
) -> list[str]:
    """Suggest analytical NL questions for a Genie space via the LLM service."""
    return llm.suggest_questions(title=space.title, description=space.description, n=n)


def _is_aggregate_numeric(v: Any) -> bool:
    if isinstance(v, bool):
        return False
    return isinstance(v, (int, float))


def _format_sample_numeric(k: str, v: int | float) -> str:
    if abs(v) >= 1000:
        return f"{k}={v:,.0f}"
    return f"{k}={v:.4g}"


def summarize_widget_rows(rows: list[dict], max_rows: int = 5) -> str:
    """Render up to max_rows of a widget's SQL result as a compact text
    block the LLM can quote. Empty/None on empty input.

    Format:
      <N> row(s) (showing first <K> if truncated):
        col_a=val | col_b=val | ...
        col_a=val | col_b=val | ...
      Numeric aggregates:
        col_b: count=..., sum=..., mean=..., min=..., max=...
    """
    if not rows:
        return ""
    head = rows[:max_rows]
    n = len(rows)
    lines: list[str] = []
    if n > max_rows:
        lines.append(f"{n} rows (showing first {max_rows}):")
    else:
        lines.append(f"{n} row(s):")
    for r in head:
        parts: list[str] = []
        for k, v in r.items():
            if v is None:
                parts.append(f"{k}=null")
            elif isinstance(v, bool):
                parts.append(f"{k}={v}")
            elif isinstance(v, (int, float)):
                parts.append(_format_sample_numeric(k, v))
            else:
                # Truncate long strings to avoid blowing up the prompt
                s = str(v)
                if len(s) > 80:
                    s = s[:77] + "..."
                parts.append(f"{k}={s}")
        lines.append("  " + " | ".join(parts))

    keys_ordered: list[str] = []
    seen_cols: set[str] = set()
    for r in rows:
        for k in r:
            if k not in seen_cols:
                seen_cols.add(k)
                keys_ordered.append(k)

    agg_lines: list[str] = []
    for col in keys_ordered:
        vals: list[float] = []
        for r in rows:
            if col not in r:
                continue
            v = r[col]
            if v is None or v == "":
                continue
            if not _is_aggregate_numeric(v):
                continue
            vals.append(float(v))
        if not vals:
            continue
        cnt = len(vals)
        total = sum(vals)
        mean = total / cnt
        agg_lines.append(
            f"  {col}: count={cnt}, sum={total}, mean={mean}, "
            f"min={min(vals)}, max={max(vals)}"
        )

    if agg_lines:
        lines.append("Numeric aggregates:")
        lines.extend(agg_lines)

    return "\n".join(lines)
