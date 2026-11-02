"""Every endpoint's real answer fits the model that describes it, and for the small answers the model names every key,
so a renamed or forgotten key in the code shows up here."""
import io
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from ragevalkit.core.config import Config
from ragevalkit.main import create_app
from ragevalkit.schemas.app_info import AppInfo, Features, Health
from ragevalkit.schemas.evaluation.responses import (
    IssueOut,
    Recommendation,
    RunIssues,
    RunPreview,
    RunSnapshot,
    VersionDetail,
    VersionSummary,
)
from ragevalkit.schemas.sign_in import Acknowledged, SignedInUser
from ragevalkit.schemas.testcase_generator import GenerationLimits
from ragevalkit.schemas.testcase_library import (
    DeletedTestCases,
    Group,
    GroupDeleted,
    GroupHistory,
    GroupImported,
    GroupsOfTestCase,
    GroupWithHistory,
    ImportPreview,
    ImportResult,
    LibraryTestCase,
    MemberAdded,
    MemberRemoved,
    MembersAdded,
    MembersRemoved,
    StatusesUpdated,
    StatusOfTestCase,
)

SAMPLE = Path(__file__).parents[2] / "examples" / "test_cases.csv"


@pytest.fixture
def served(tmp_path):
    config = Config(data_dir=tmp_path, require_login=False, run_semantic_similarity=False, run_bm25=False)
    app = create_app(config, fn=lambda q: "Refunds are allowed within 30 days.",
                     judge_fn=lambda q, e, g, m: {"answer_marks": 8, "material_marks": 7})
    app.state.manager._llm_judge = SimpleNamespace(summarize_run=lambda stats: None)
    yield TestClient(app)
    app.state.store.close()


def fits(model, body, *, every_key_named: bool):
    parsed = model.model_validate(body)
    if every_key_named:
        assert not parsed.model_extra, f"{model.__name__} does not name: {sorted(parsed.model_extra)}"
    assert parsed.model_dump() == body            # nothing added, nothing lost on the way out
    return parsed


def test_the_small_answers_are_fully_described(served):
    client = served
    upload = {"file": ("test_cases.csv", SAMPLE.read_bytes(), "text/csv")}
    fits(ImportPreview, client.post("/api/test-cases/import/preview", files=upload).json(), every_key_named=False)
    fits(ImportResult, client.post("/api/test-cases/import", files=upload).json(), every_key_named=True)

    cases = client.get("/api/test-cases").json()
    for case in cases:
        fits(LibraryTestCase, case, every_key_named=True)
    tc_id = cases[0]["tc_id"]
    fits(LibraryTestCase, client.get(f"/api/test-cases/{tc_id}").json(), every_key_named=True)
    fits(LibraryTestCase, client.patch(f"/api/test-cases/{tc_id}", json={"expected_answer": "changed"}).json(), every_key_named=True)
    fits(StatusesUpdated, client.post("/api/test-cases/status", json={"tc_ids": [tc_id], "status": "active"}).json(), every_key_named=True)
    fits(StatusOfTestCase, client.patch(f"/api/test-cases/{tc_id}/status", json={"status": "active"}).json(), every_key_named=True)

    groups = client.get("/api/groups").json()
    for group in groups:
        fits(GroupWithHistory, group, every_key_named=True)
    group_id = groups[0]["group_id"]
    fits(Group, client.post("/api/groups", json={"name": "Extra"}).json(), every_key_named=True)
    fits(GroupHistory, client.get(f"/api/groups/{group_id}/runs").json(), every_key_named=True)
    fits(GroupsOfTestCase, client.put(f"/api/test-cases/{tc_id}/groups", json={"group_ids": [group_id]}).json(), every_key_named=True)
    fits(MembersAdded, client.post(f"/api/groups/{group_id}/members", json={"tc_ids": [tc_id]}).json(), every_key_named=True)
    fits(MembersRemoved, client.post(f"/api/groups/{group_id}/members/remove", json={"tc_ids": [tc_id]}).json(), every_key_named=True)
    fits(MemberAdded, client.post(f"/api/groups/{group_id}/members/{tc_id}").json(), every_key_named=True)
    fits(MemberRemoved, client.delete(f"/api/groups/{group_id}/members/{tc_id}").json(), every_key_named=True)
    workbook = io.BytesIO()
    pd.read_csv(SAMPLE).to_excel(workbook, index=False)               # this older endpoint reads Excel files only
    excel = {"file": ("cases.xlsx", workbook.getvalue(), "application/octet-stream")}
    fits(GroupImported, client.post(f"/api/groups/{group_id}/import", files=excel).json(), every_key_named=True)
    fits(GroupDeleted, client.delete(f"/api/groups/{group_id}").json(), every_key_named=True)
    fits(DeletedTestCases, client.post("/api/test-cases/delete", json={"tc_ids": [tc_id]}).json(), every_key_named=True)


def test_a_run_and_its_results_are_described(served):
    client = served
    upload = {"file": ("test_cases.csv", SAMPLE.read_bytes(), "text/csv")}
    client.post("/api/test-cases/import", files=upload)
    group_id = next(g["group_id"] for g in client.get("/api/groups").json() if g["name"] == "Billing")
    fits(RunPreview, client.post("/api/runs/preview", json={"group_ids": [group_id], "tc_ids": [], "status_filter": "active", "include_context": True}).json(), every_key_named=True)

    started = client.post("/api/runs", data={"version": "1", "group_ids": json.dumps([group_id])}).json()
    fits(RunSnapshot, started, every_key_named=True)
    deadline = time.time() + 20
    while not client.get("/api/versions").json() and time.time() < deadline:
        time.sleep(0.05)

    for summary in client.get("/api/versions").json():
        fits(VersionSummary, summary, every_key_named=False)
    detail = fits(VersionDetail, client.get("/api/versions/1").json(), every_key_named=False)
    assert detail.rows and detail.rows[0].question
    issues = fits(RunIssues, client.get(f"/api/runs/{started['run_id']}/issues").json(), every_key_named=True)
    assert all(isinstance(issue, IssueOut) for issue in issues.issues)
    fits(Recommendation, client.get("/api/recommendation").json(), every_key_named=True)


def test_the_app_describes_itself(served):
    client = served
    fits(Health, client.get("/api/health").json(), every_key_named=True)
    fits(Features, client.get("/api/features").json(), every_key_named=True)
    fits(GenerationLimits, client.get("/api/generate/limits").json(), every_key_named=True)
    fits(SignedInUser, client.post("/api/auth/login", json={"username": "a", "password": "b"}).json(), every_key_named=True)
    fits(Acknowledged, client.post("/api/auth/logout").json(), every_key_named=True)
    assert fits(AppInfo, client.get("/api/info").json(), every_key_named=True).name == "RAG Evaluator"


def test_the_name_is_public_because_the_login_page_shows_it(tmp_path):
    app = create_app(Config(data_dir=tmp_path), fn=lambda q: "a")          # sign-in required, nobody signed in
    try:
        client = TestClient(app)
        assert client.get("/api/info").status_code == 200
        assert client.get("/api/features").status_code == 401
    finally:
        app.state.store.close()
