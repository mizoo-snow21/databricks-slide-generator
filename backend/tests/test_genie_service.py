"""Unit tests for genie_service (mocked WorkspaceClient.genie, no network)."""

from __future__ import annotations

import asyncio
from enum import Enum
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from services.genie_service import (
    GenieAnswer,
    GenieSpaceInfo,
    ask,
    ask_many,
    get_space,
    list_spaces,
    suggest_questions,
)
from services.llm_service import LLMService


class MessageStatus(Enum):
    EXECUTING_QUERY = 1
    COMPLETED = 2
    FAILED = 3
    ASKING_AI = 4


class StatementState(Enum):
    SUCCEEDED = 1
    FAILED = 2


def _make_client() -> MagicMock:
    client = MagicMock()
    client.genie = MagicMock()
    return client


def test_list_spaces_maps_fields() -> None:
    space = SimpleNamespace(space_id="s1", title="Sales Genie")
    resp = SimpleNamespace(spaces=[space], next_page_token="more")
    client = _make_client()
    client.genie.list_spaces.return_value = resp

    result = list_spaces(client)

    assert result == [
        GenieSpaceInfo(space_id="s1", title="Sales Genie", description=""),
    ]
    client.genie.list_spaces.assert_called_once_with()


def test_get_space_maps_fields() -> None:
    client = _make_client()
    client.genie.get_space.return_value = SimpleNamespace(
        title="T",
        description="Desc",
        warehouse_id="wh-9",
    )

    result = get_space(client, "s1")

    assert result == GenieSpaceInfo(
        space_id="s1",
        title="T",
        description="Desc",
        warehouse_id="wh-9",
    )
    client.genie.get_space.assert_called_once_with("s1")


def test_ask_completed_returns_rows() -> None:
    client = _make_client()
    client.genie.start_conversation.return_value = SimpleNamespace(
        response=SimpleNamespace(conversation_id="c1", message_id="m1"),
    )

    query_obj = SimpleNamespace(query="SELECT 1")
    attachment = SimpleNamespace(
        attachment_id="a1",
        query=query_obj,
        text=None,
    )
    completed = SimpleNamespace(
        status=MessageStatus.COMPLETED,
        attachments=[attachment],
    )
    executing = SimpleNamespace(
        status=MessageStatus.EXECUTING_QUERY,
        attachments=[],
    )
    client.genie.get_message.side_effect = [executing, completed]

    col_a = SimpleNamespace(name="a")
    col_b = SimpleNamespace(name="b")
    result_fetch = SimpleNamespace(
        statement_response=SimpleNamespace(
            status=SimpleNamespace(state=StatementState.SUCCEEDED),
            manifest=SimpleNamespace(
                schema=SimpleNamespace(columns=[col_a, col_b]),
            ),
            result=SimpleNamespace(data_array=[["x", 1]]),
        ),
    )
    client.genie.get_message_query_result_by_attachment.return_value = result_fetch

    with patch("services.genie_service.time.sleep"):
        answer = ask(
            client,
            "space-1",
            "How many rows?",
            poll_interval_s=0,
            max_polls=5,
        )

    assert answer == GenieAnswer(
        question="How many rows?",
        sql="SELECT 1",
        columns=["a", "b"],
        rows=[{"a": "x", "b": 1}],
        status="ok",
        error=None,
    )
    client.genie.get_message_query_result_by_attachment.assert_called_once_with(
        "space-1", "c1", "m1", "a1",
    )


def test_ask_text_only_is_failed() -> None:
    client = _make_client()
    client.genie.start_conversation.return_value = SimpleNamespace(
        response=SimpleNamespace(conversation_id="c1", message_id="m1"),
    )
    attachment = SimpleNamespace(
        attachment_id="a1",
        query=None,
        text="Here is the answer in prose.",
    )
    completed = SimpleNamespace(
        status=MessageStatus.COMPLETED,
        attachments=[attachment],
    )
    client.genie.get_message.return_value = completed

    answer = ask(client, "space-1", "Explain revenue", max_polls=3, poll_interval_s=0)

    assert answer.status == "failed"
    assert answer.rows == []
    assert answer.sql is None
    assert answer.error is not None
    client.genie.get_message_query_result_by_attachment.assert_not_called()


def test_ask_error_result_is_failed() -> None:
    client = _make_client()
    client.genie.start_conversation.return_value = SimpleNamespace(
        response=SimpleNamespace(conversation_id="c1", message_id="m1"),
    )
    attachment = SimpleNamespace(
        attachment_id="a1",
        query=SimpleNamespace(query="SELECT bad"),
        text=None,
    )
    completed = SimpleNamespace(
        status=MessageStatus.COMPLETED,
        attachments=[attachment],
    )
    client.genie.get_message.return_value = completed

    err_col = SimpleNamespace(name="error_message")
    result_fetch = SimpleNamespace(
        statement_response=SimpleNamespace(
            status=SimpleNamespace(state=StatementState.FAILED),
            manifest=SimpleNamespace(
                schema=SimpleNamespace(columns=[err_col]),
            ),
            result=SimpleNamespace(
                data_array=[["Insufficient privileges"]],
            ),
        ),
    )
    client.genie.get_message_query_result_by_attachment.return_value = result_fetch

    answer = ask(client, "space-1", "Q?", max_polls=3, poll_interval_s=0)

    assert answer.status == "failed"
    assert answer.rows == []
    assert answer.error is not None
    assert "FAILED" in (answer.error or "")


def test_ask_error_message_column_with_succeeded_state() -> None:
    client = _make_client()
    client.genie.start_conversation.return_value = SimpleNamespace(
        response=SimpleNamespace(conversation_id="c1", message_id="m1"),
    )
    attachment = SimpleNamespace(
        attachment_id="a1",
        query=SimpleNamespace(query="SELECT bad"),
        text=None,
    )
    completed = SimpleNamespace(
        status=MessageStatus.COMPLETED,
        attachments=[attachment],
    )
    client.genie.get_message.return_value = completed

    err_col = SimpleNamespace(name="error_message")
    result_fetch = SimpleNamespace(
        statement_response=SimpleNamespace(
            status=SimpleNamespace(state=StatementState.SUCCEEDED),
            manifest=SimpleNamespace(
                schema=SimpleNamespace(columns=[err_col]),
            ),
            result=SimpleNamespace(
                data_array=[["Insufficient privileges"]],
            ),
        ),
    )
    client.genie.get_message_query_result_by_attachment.return_value = result_fetch

    answer = ask(client, "space-1", "Q?", max_polls=3, poll_interval_s=0)

    assert answer.status == "failed"
    assert answer.error == "Insufficient privileges"


def test_ask_succeeded_with_none_manifest_is_failed() -> None:
    client = _make_client()
    client.genie.start_conversation.return_value = SimpleNamespace(
        response=SimpleNamespace(conversation_id="c1", message_id="m1"),
    )
    attachment = SimpleNamespace(
        attachment_id="a1",
        query=SimpleNamespace(query="SELECT 1"),
        text=None,
    )
    completed = SimpleNamespace(
        status=MessageStatus.COMPLETED,
        attachments=[attachment],
    )
    client.genie.get_message.return_value = completed

    result_fetch = SimpleNamespace(
        statement_response=SimpleNamespace(
            status=SimpleNamespace(state=StatementState.SUCCEEDED),
            manifest=None,
            result=SimpleNamespace(data_array=[["x"]]),
        ),
    )
    client.genie.get_message_query_result_by_attachment.return_value = result_fetch

    answer = ask(client, "space-1", "Q?", max_polls=3, poll_interval_s=0)

    assert answer.status == "failed"
    assert answer.error is not None


def test_ask_succeeded_with_none_result_is_failed() -> None:
    client = _make_client()
    client.genie.start_conversation.return_value = SimpleNamespace(
        response=SimpleNamespace(conversation_id="c1", message_id="m1"),
    )
    attachment = SimpleNamespace(
        attachment_id="a1",
        query=SimpleNamespace(query="SELECT 1"),
        text=None,
    )
    completed = SimpleNamespace(
        status=MessageStatus.COMPLETED,
        attachments=[attachment],
    )
    client.genie.get_message.return_value = completed

    col = SimpleNamespace(name="a")
    result_fetch = SimpleNamespace(
        statement_response=SimpleNamespace(
            status=SimpleNamespace(state=StatementState.SUCCEEDED),
            manifest=SimpleNamespace(
                schema=SimpleNamespace(columns=[col]),
            ),
            result=None,
        ),
    )
    client.genie.get_message_query_result_by_attachment.return_value = result_fetch

    answer = ask(client, "space-1", "Q?", max_polls=3, poll_interval_s=0)

    assert answer.status == "failed"
    assert answer.error is not None


def test_ask_get_message_raises_returns_failed() -> None:
    client = _make_client()
    client.genie.start_conversation.return_value = SimpleNamespace(
        response=SimpleNamespace(conversation_id="c1", message_id="m1"),
    )
    client.genie.get_message.side_effect = RuntimeError("network down")

    answer = ask(client, "space-1", "Q?", max_polls=3, poll_interval_s=0)

    assert answer.status == "failed"
    assert "Genie request failed" in (answer.error or "")
    assert "network down" in (answer.error or "")


def test_ask_failed_status() -> None:
    client = _make_client()
    client.genie.start_conversation.return_value = SimpleNamespace(
        response=SimpleNamespace(conversation_id="c1", message_id="m1"),
    )
    failed = SimpleNamespace(status=MessageStatus.FAILED, attachments=[])
    client.genie.get_message.return_value = failed

    answer = ask(client, "space-1", "Q?", max_polls=3, poll_interval_s=0)

    assert answer.status == "failed"
    assert answer.rows == []
    assert answer.error is not None


def test_ask_timeout() -> None:
    client = _make_client()
    client.genie.start_conversation.return_value = SimpleNamespace(
        response=SimpleNamespace(conversation_id="c1", message_id="m1"),
    )
    in_progress = SimpleNamespace(status=MessageStatus.ASKING_AI, attachments=[])
    client.genie.get_message.return_value = in_progress

    with patch("services.genie_service.time.sleep") as sleep_mock:
        answer = ask(
            client,
            "space-1",
            "Q?",
            poll_interval_s=0,
            max_polls=2,
        )

    assert answer.status == "failed"
    assert answer.rows == []
    assert "timeout" in (answer.error or "").lower()
    assert sleep_mock.call_count == 1


def _ok_answer(question: str) -> GenieAnswer:
    return GenieAnswer(question=question, status="ok", error=None)


def _failed_answer(question: str, error: str) -> GenieAnswer:
    return GenieAnswer(question=question, status="failed", error=error)


def test_ask_many_collects_failures_into_warnings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_ask(_client: MagicMock, _space_id: str, question: str, **kwargs: object) -> GenieAnswer:
        if question == "Q2":
            return _failed_answer("Q2", "boom")
        return _ok_answer(question)

    monkeypatch.setattr("services.genie_service.ask", fake_ask)
    client = _make_client()

    ok_answers, warnings = asyncio.run(
        ask_many(client, "space-1", ["Q1", "Q2", "Q3"]),
    )

    assert [a.question for a in ok_answers] == ["Q1", "Q3"]
    assert warnings == ["Q2: boom"]


def test_ask_many_all_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_ask(_client: MagicMock, _space_id: str, question: str, **kwargs: object) -> GenieAnswer:
        return _failed_answer(question, "nope")

    monkeypatch.setattr("services.genie_service.ask", fake_ask)
    client = _make_client()
    questions = ["Q1", "Q2", "Q3"]

    ok_answers, warnings = asyncio.run(
        ask_many(client, "space-1", questions),
    )

    assert ok_answers == []
    assert len(warnings) == len(questions)


def test_ask_many_empty() -> None:
    client = _make_client()

    ok_answers, warnings = asyncio.run(ask_many(client, "space-1", []))

    assert ok_answers == []
    assert warnings == []


def test_suggest_questions_parses_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = LLMService(workspace_client=MagicMock())
    monkeypatch.setattr(
        llm,
        "_foundation_model_chat_sync",
        lambda *args, **kwargs: "1. Q one\n- Q two\n\n* Q three",
    )
    space = GenieSpaceInfo(space_id="s1", title="Sales", description="Revenue data")

    result = suggest_questions(llm, space, n=8)

    assert result == ["Q one", "Q two", "Q three"]


def test_suggest_questions_caps_at_n(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = LLMService(workspace_client=MagicMock())
    ten_lines = "\n".join(f"Question {i}" for i in range(1, 11))
    monkeypatch.setattr(
        llm,
        "_foundation_model_chat_sync",
        lambda *args, **kwargs: ten_lines,
    )
    space = GenieSpaceInfo(space_id="s1", title="T", description="D")

    result = suggest_questions(llm, space, n=3)

    assert len(result) == 3
