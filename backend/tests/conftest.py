"""Shared pytest fixtures for backend tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    from main import app

    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def stub_workspace_client():
    ws = MagicMock()
    ws.current_user.me.return_value = MagicMock(user_name="stub-user", groups=[])
    ws.warehouses.list.return_value = []
    ws.lakeview.list.return_value = iter([])
    return ws


@pytest.fixture
def stub_obo_dependency(stub_workspace_client):
    from main import app

    from auth.user_workspace import get_sp_workspace_client, get_user_workspace_client

    app.dependency_overrides[get_user_workspace_client] = lambda: stub_workspace_client
    app.dependency_overrides[get_sp_workspace_client] = lambda: stub_workspace_client
    yield stub_workspace_client
