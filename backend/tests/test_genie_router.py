"""Tests for /api/genie REST routes."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from auth.user_workspace import get_user_workspace_client
from main import app
from routers.genie import get_llm_service
from services.genie_service import GenieSpaceInfo
from services.llm_service import LLMService


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_list_spaces_endpoint_returns_spaces(client: TestClient) -> None:
    mock_ws = MagicMock()
    app.dependency_overrides[get_user_workspace_client] = lambda: mock_ws

    space = GenieSpaceInfo(space_id="s1", title="T", description="d")
    with patch("routers.genie.genie_service.list_spaces", return_value=[space]):
        response = client.get("/api/genie/spaces")

    assert response.status_code == 200
    assert response.json() == [
        {"space_id": "s1", "title": "T", "description": "d", "warehouse_id": None}
    ]


def test_get_space_endpoint(client: TestClient) -> None:
    mock_ws = MagicMock()
    app.dependency_overrides[get_user_workspace_client] = lambda: mock_ws

    space = GenieSpaceInfo(space_id="s1", title="T", description="d")
    with patch("routers.genie.genie_service.get_space", return_value=space) as mock_get:
        response = client.get("/api/genie/spaces/s1")

    assert response.status_code == 200
    assert response.json() == {
        "space_id": "s1",
        "title": "T",
        "description": "d",
        "warehouse_id": None,
    }
    mock_get.assert_called_once_with(mock_ws, "s1")


def test_suggested_questions_endpoint(client: TestClient) -> None:
    mock_ws = MagicMock()
    mock_llm = MagicMock(spec=LLMService)
    app.dependency_overrides[get_user_workspace_client] = lambda: mock_ws
    app.dependency_overrides[get_llm_service] = lambda: mock_llm

    space = GenieSpaceInfo(space_id="s1", title="T", description="d")
    with (
        patch("routers.genie.genie_service.get_space", return_value=space) as mock_get,
        patch(
            "routers.genie.genie_service.suggest_questions",
            return_value=["q1", "q2"],
        ) as mock_suggest,
    ):
        response = client.post("/api/genie/spaces/s1/suggested-questions")

    assert response.status_code == 200
    assert response.json() == {"questions": ["q1", "q2"]}
    mock_get.assert_called_once_with(mock_ws, "s1")
    mock_suggest.assert_called_once_with(mock_llm, space, n=8)


def test_spaces_endpoint_workspace_unavailable_503(client: TestClient) -> None:
    mock_ws = MagicMock()
    app.dependency_overrides[get_user_workspace_client] = lambda: mock_ws

    with patch(
        "routers.genie.genie_service.list_spaces",
        side_effect=Exception("no auth"),
    ):
        response = client.get("/api/genie/spaces")

    assert response.status_code == 503
    assert response.json()["detail"] == "Genie workspace unavailable: no auth"


def test_suggested_questions_llm_failure_returns_502(client: TestClient) -> None:
    mock_ws = MagicMock()
    mock_llm = MagicMock(spec=LLMService)
    app.dependency_overrides[get_user_workspace_client] = lambda: mock_ws
    app.dependency_overrides[get_llm_service] = lambda: mock_llm

    space = GenieSpaceInfo(space_id="s1", title="T", description="d")
    with (
        patch("routers.genie.genie_service.get_space", return_value=space),
        patch(
            "routers.genie.genie_service.suggest_questions",
            side_effect=Exception("llm down"),
        ),
    ):
        response = client.post("/api/genie/spaces/s1/suggested-questions")

    assert response.status_code == 502
    assert response.json()["detail"] == "Question suggestion failed"


def test_suggested_questions_get_space_failure_returns_503(client: TestClient) -> None:
    mock_ws = MagicMock()
    mock_llm = MagicMock(spec=LLMService)
    app.dependency_overrides[get_user_workspace_client] = lambda: mock_ws
    app.dependency_overrides[get_llm_service] = lambda: mock_llm

    with patch(
        "routers.genie.genie_service.get_space",
        side_effect=Exception("no auth"),
    ):
        response = client.post("/api/genie/spaces/s1/suggested-questions")

    assert response.status_code == 503
    assert response.json()["detail"].startswith("Genie workspace unavailable")
