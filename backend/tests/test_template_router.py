"""Tests for /api/templates REST routes."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from main import app
from routers.templates import templates_service


@pytest.fixture(autouse=True)
def clear_template_store() -> None:
    templates_service._memory.clear()
    yield
    templates_service._memory.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_list_templates_empty(client: TestClient) -> None:
    response = client.get("/api/templates")
    assert response.status_code == 200
    assert response.json() == []


def test_create_and_get_template(client: TestClient) -> None:
    payload = {
        "name": "Corp Deck",
        "google_slides_template_id": "gslides-template-abc",
    }
    create_resp = client.post("/api/templates", json=payload)
    assert create_resp.status_code == 201
    body = create_resp.json()
    assert body["name"] == "Corp Deck"
    assert body["google_slides_template_id"] == "gslides-template-abc"
    template_id = body["id"]
    assert template_id

    get_resp = client.get(f"/api/templates/{template_id}")
    assert get_resp.status_code == 200
    got = get_resp.json()
    assert got["id"] == template_id
    assert got["name"] == "Corp Deck"


def test_get_nonexistent_template(client: TestClient) -> None:
    response = client.get("/api/templates/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_delete_template(client: TestClient) -> None:
    created = client.post(
        "/api/templates",
        json={"name": "ToDelete", "google_slides_template_id": "g-del"},
    ).json()
    template_id = created["id"]

    response = client.delete(f"/api/templates/{template_id}")
    assert response.status_code == 204
    assert response.content == b""

    assert client.get(f"/api/templates/{template_id}").status_code == 404


def test_delete_nonexistent_template(client: TestClient) -> None:
    missing_id = str(uuid.uuid4())
    response = client.delete(f"/api/templates/{missing_id}")
    assert response.status_code == 404
