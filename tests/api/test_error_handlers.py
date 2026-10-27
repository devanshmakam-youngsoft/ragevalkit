"""Errors raised anywhere become one response shape: plain message plus a short code."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ragevalkit.api.error_handlers import register_error_handlers
from ragevalkit.evaluation.exceptions import RunBusy
from ragevalkit.exceptions import InvalidInput, NotFoundError, TooLargeError
from ragevalkit.storage.exceptions import ConflictError, VersionNotFound


@pytest.fixture
def client():
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/raise/{kind}")
    def raise_error(kind: str):
        errors = {
            "missing": NotFoundError("Run not found"),
            "version": VersionNotFound("Version v9 not found"),
            "large": TooLargeError("File is too large"),
            "conflict": ConflictError("Version v1 already exists"),
            "busy": RunBusy("A run is already in progress"),
            "invalid": InvalidInput("Name cannot be empty"),
            "boom": RuntimeError("secret internal detail"),
        }
        raise errors[kind]

    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("kind,status,code", [
    ("missing", 404, "not_found"),
    ("version", 404, "not_found"),
    ("large", 413, "too_large"),
    ("conflict", 409, "conflict"),
    ("busy", 409, "busy"),
    ("invalid", 422, "invalid_input"),
])
def test_known_errors_map_to_status_and_code(client, kind, status, code):
    response = client.get(f"/raise/{kind}")
    assert response.status_code == status
    assert response.json()["code"] == code
    assert "'" not in response.json()["detail"][:1]      # no KeyError-style quoting


def test_unexpected_error_hides_internals_and_gives_a_reference(client):
    response = client.get("/raise/boom")
    body = response.json()
    assert response.status_code == 500
    assert body["code"] == "server_error"
    assert "secret internal detail" not in body["detail"]
    assert len(body["reference"]) == 8
