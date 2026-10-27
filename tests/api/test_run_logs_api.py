"""The dashboard can read a run's problems and download its log file, and nothing outside the log folder."""
import pytest
from fastapi.testclient import TestClient

from ragevalkit.api import create_app
from ragevalkit.config import Config


@pytest.fixture
def served(tmp_path):
    config = Config(store_path=tmp_path / "eval_store.json", require_login=False)
    app = create_app(config, fn=lambda question: "answer")
    yield TestClient(app), app, config
    app.state.store.close()


def _save_version(app, name, log_file):
    app.state.store.write(name, {"version": name, "total_rows": 0, "log_file": log_file, "issues": []}, [])


def test_the_log_of_a_version_can_be_downloaded(served):
    client, app, config = served
    (config.logs_dir / "runs").mkdir(parents=True)
    (config.logs_dir / "runs" / "20260101-000000_v1.log").write_text("Run v1 started", encoding="utf-8")
    _save_version(app, "v1", "20260101-000000_v1.log")
    response = client.get("/api/versions/v1/log")
    assert response.status_code == 200 and response.text == "Run v1 started"


def test_a_log_name_that_points_outside_the_log_folder_is_not_followed(served):
    client, app, config = served
    (config.logs_dir).mkdir(parents=True)
    (config.logs_dir / "secret.txt").write_text("not a run log", encoding="utf-8")
    _save_version(app, "v2", "../secret.txt")
    response = client.get("/api/versions/v2/log")
    assert response.status_code == 404 and response.json()["code"] == "not_found"


def test_the_issues_of_an_unknown_run_are_not_found(served):
    client, _, _ = served
    assert client.get("/api/runs/nope/issues").status_code == 404
