"""The guides can be listed and read inside the dashboard."""
import pytest
from fastapi.testclient import TestClient

from ragevalkit.api import create_app
from ragevalkit.config import Config
from ragevalkit.guides import GUIDES


@pytest.fixture
def client(tmp_path):
    app = create_app(Config(store_path=tmp_path / "eval_store.json", require_login=False), fn=lambda question: "answer")
    yield TestClient(app)
    app.state.store.close()


def test_every_listed_guide_can_be_read_as_a_page(client):
    listed = client.get("/api/help/guides").json()
    assert [g["id"] for g in listed] == [g.guide_id for g in GUIDES]
    for guide in listed:
        page = client.get(f"/api/help/guides/{guide['id']}")
        assert page.status_code == 200 and "<html" in page.text.lower()


def test_an_unknown_guide_is_not_found(client):
    assert client.get("/api/help/guides/missing").json()["code"] == "not_found"


def test_the_guides_need_a_sign_in_when_login_is_required(tmp_path):
    app = create_app(Config(store_path=tmp_path / "eval_store.json"), fn=lambda question: "answer")
    try:
        assert TestClient(app).get("/api/help/guides").status_code == 401
    finally:
        app.state.store.close()
