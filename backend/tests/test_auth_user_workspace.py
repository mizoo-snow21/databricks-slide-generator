"""Tests for OBO user workspace client resolution (Databricks Apps vs local dev)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from auth.user_workspace import get_sp_workspace_client, get_user_workspace_client


def test_get_sp_workspace_client_returns_default_workspace_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABRICKS_APP_NAME", raising=False)
    fake = MagicMock()
    with patch("auth.user_workspace.WorkspaceClient") as mock_wsCtor:
        mock_wsCtor.return_value = fake
        result = get_sp_workspace_client()

    assert result is fake
    mock_wsCtor.assert_called_once_with()


def test_get_sp_workspace_client_returns_none_when_default_client_raises() -> None:
    def boom() -> None:
        raise RuntimeError("no credentials")

    with patch("auth.user_workspace.WorkspaceClient", side_effect=boom):
        result = get_sp_workspace_client()

    assert result is None


def test_get_user_workspace_client_uses_user_token_when_header_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABRICKS_APP_NAME", raising=False)
    monkeypatch.setenv("DATABRICKS_HOST", "https://dbc.test")
    token = "obo-user-token"

    captured: dict[str, object] = {}

    class FakeWS:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    with patch("auth.user_workspace.WorkspaceClient", FakeWS):
        result = get_user_workspace_client(x_forwarded_access_token=token)

    assert isinstance(result, FakeWS)
    assert captured["host"] == "https://dbc.test"
    assert captured["token"] == token
    assert captured["auth_type"] == "pat"
    assert captured["client_id"] == ""
    assert captured["client_secret"] == ""


def test_get_user_workspace_client_raises_503_when_apps_runtime_and_no_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABRICKS_APP_NAME", "genie-slide")

    with pytest.raises(HTTPException) as ctx:
        get_user_workspace_client(x_forwarded_access_token=None)

    assert ctx.value.status_code == 503
    detail = ctx.value.detail
    assert isinstance(detail, str)
    assert "user_authorization.scopes" in detail
    assert "On-behalf-of-user authentication is not configured" in detail


def test_get_user_workspace_client_raises_503_when_apps_runtime_and_header_present_but_host_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABRICKS_APP_NAME", "genie-slide")
    monkeypatch.delenv("DATABRICKS_HOST", raising=False)

    with pytest.raises(HTTPException) as ctx:
        get_user_workspace_client(x_forwarded_access_token="tok")

    assert ctx.value.status_code == 503
    detail = ctx.value.detail
    assert isinstance(detail, str)
    assert "DATABRICKS_HOST" in detail


def test_get_user_workspace_client_local_dev_no_header_uses_default_workspace_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABRICKS_APP_NAME", raising=False)
    fake = MagicMock()
    with patch("auth.user_workspace.WorkspaceClient") as mock_wsCtor:
        mock_wsCtor.return_value = fake
        result = get_user_workspace_client(x_forwarded_access_token=None)

    assert result is fake
    mock_wsCtor.assert_called_once_with()


def test_get_user_workspace_client_local_dev_returns_none_when_default_client_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABRICKS_APP_NAME", raising=False)

    def boom() -> None:
        raise RuntimeError("no credentials")

    with patch("auth.user_workspace.WorkspaceClient", side_effect=boom):
        result = get_user_workspace_client(x_forwarded_access_token=None)

    assert result is None
