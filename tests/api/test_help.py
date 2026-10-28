"""The guide can be read inside the dashboard, and is only there when it is switched on."""
import pytest
from fastapi.testclient import TestClient

from ragevalkit.api import create_app
from ragevalkit.config import Config


def _client(tmp_path, **options):
    app = create_app(Config(store_path=tmp_path / "eval_store.json", require_login=False, **options), fn=lambda question: "answer")
    return TestClient(app), app


@pytest.fixture
def served(tmp_path):
    client, app = _client(tmp_path)
    yield client
    app.state.store.close()


def test_the_guide_is_a_complete_page_and_the_dashboard_is_told_to_show_it(served):
    page = served.get("/api/help/guide")
    assert page.status_code == 200 and page.text.lower().startswith("<!doctype html")
    assert served.get("/api/features").json() == {"guide": True}


def test_with_show_guide_off_the_guide_is_hidden_and_not_served(tmp_path):
    client, app = _client(tmp_path, show_guide=False)
    try:
        assert client.get("/api/features").json() == {"guide": False}
        assert client.get("/api/help/guide").json()["code"] == "not_found"
    finally:
        app.state.store.close()


def test_the_guide_needs_a_sign_in_when_login_is_required(tmp_path):
    app = create_app(Config(store_path=tmp_path / "eval_store.json"), fn=lambda question: "answer")
    try:
        assert TestClient(app).get("/api/help/guide").status_code == 401
    finally:
        app.state.store.close()
