"""Recommendation and group history: computed from saved scores, over non-archived runs only."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from ragevalkit.config import Config
from ragevalkit.recommend import group_overview, recommend
from ragevalkit.server import create_app
from ragevalkit.store import EvalStore, build_scores, build_summary


def run(version, answer, material, time, *, rows=8, failed=0, archived=False, stopped=False, groups=None):
    r = {
        "version": str(version), "date": f"2026-01-{int(version):02d}T00:00:00+00:00",
        "total_rows": rows, "failed_rows": failed, "avg_answer_marks": answer,
        "avg_material_marks": material, "avg_total_time": time, "archived": archived, "stopped": stopped,
    }
    if groups:
        r["group_stats"] = groups
    return r


def test_quality_beats_speed_and_speed_breaks_a_near_tie():
    assert recommend([run(1, 8, 8, 1.0), run(2, 9.3, 10, 2.0)])["best"] == "2"
    assert recommend([run(1, 9.3, 10, 2.0), run(2, 9.2, 10, 1.2)])["best"] == "2"


def test_a_high_answer_with_poor_material_loses_to_a_balanced_run():
    assert recommend([run(1, 9.5, 5, 0.8), run(2, 9.0, 9.5, 1.6)])["best"] == "2"


def test_archiving_the_recommended_version_changes_the_recommendation():
    versions = [run(1, 7, 7, 1.0), run(2, 8, 8, 1.0), run(3, 9, 9, 1.0)]
    assert recommend(versions)["best"] == "3"
    versions[2]["archived"] = True
    result = recommend(versions)
    assert result["best"] == "2"
    assert "3" not in result["qualities"]            # archived runs are not compared at all


def test_a_run_with_no_material_marks_cannot_win_by_skipping_them():
    # v2 never had material graded; it must not beat v1 just because its quality is "answer only"
    result = recommend([run(1, 8, 9, 1.0), run(2, 8.5, None, 1.0)])
    assert result["basis"] == "answer_only" and "v2" in result["basis_note"]
    assert result["qualities"]["1"] == 8 and result["qualities"]["2"] == 8.5   # compared like for like
    # when every version has material, it counts
    assert recommend([run(1, 8, 9, 1.0), run(2, 8.5, 6, 1.0)])["basis"] == "weighted"


def test_failed_stopped_and_differently_sized_runs_are_never_recommended():
    result = recommend([
        run(1, 7, 7, 1), run(2, 10, 10, 1, failed=1), run(3, 10, 10, 1, stopped=True), run(4, 10, 10, 1, rows=3),
    ])
    assert result["best"] == "1"
    assert set(result["excluded"]) == {"2", "3"} and result["not_comparable"] == ["4"]


def test_time_budget_and_weights_come_from_the_caller():
    versions = [run(1, 8, 8, 5.0), run(2, 9, 9, 1.0)]
    over_budget = recommend(versions, max_time=0.5)
    assert over_budget["best"] is None and over_budget["budget_miss"] is True
    # all weight on material flips the winner
    flipped = recommend([run(1, 9, 5, 1), run(2, 7, 9, 1)], answer_weight=0.0, material_weight=1.0, tolerance=0)
    assert flipped["best"] == "2"


def test_group_overview_reports_last_run_and_best_version_so_far():
    def g(answer):
        return {"G": {"avg_answer_marks": answer, "avg_material_marks": 8, "avg_total_time": 1.0, "total_rows": 4}}

    versions = [run(1, 5, 5, 1, groups=g(6)), run(2, 5, 5, 1, groups=g(9)), run(3, 5, 5, 1, groups=g(7)), run(4, 5, 5, 1)]
    overview = group_overview(versions, "G")
    assert overview["last"]["version"] == "3"             # v4 never ran this group
    assert overview["best"]["version"] == "2"
    assert [r["version"] for r in overview["runs"]] == ["3", "2", "1"]
    versions[1]["archived"] = True                         # archive the best: it stops being "best so far"
    assert group_overview(versions, "G")["best"]["version"] == "3"
    assert group_overview(versions, "Other")["last"] is None


def test_summary_saves_detailed_scores():
    rows = [
        {"status": "ok", "type": "rag", "answer_marks": 9, "material_marks": 8, "total_time_taken": 1.0, "source_match": True},
        {"status": "ok", "type": "rag", "answer_marks": 6, "material_marks": 4, "total_time_taken": 3.0, "source_match": False},
        {"status": "ok", "type": "chat", "answer_marks": 2, "material_marks": None, "total_time_taken": 2.0},
    ]
    scores = build_scores(rows)
    assert scores["tiers"] == {"high": 1, "mid": 1, "low": 1}
    assert scores["by_type"]["rag"] == {"rows": 2, "answer_marks": 7.5, "material_marks": 6.0}
    assert scores["by_type"]["chat"]["material_marks"] is None
    assert scores["time"] == {"avg": 2.0, "p95": 3.0}
    assert scores["sources"] == {"checked": 2, "matched": 1}
    summary = build_summary("1", [{**r, "node_timings": {}} for r in rows], datetime.now(timezone.utc), "d")
    assert summary["scores"]["graded_rows"] == 3


def test_renaming_a_group_keeps_its_history(tmp_path):
    store = EvalStore(tmp_path / "s.json")
    gid = store.create_group("Old")
    summary = {"version": "1", "date": "2026-01-01T00:00:00+00:00", "dataset": "Old + Other", "group_names": ["Old"],
               "group_stats": {"Old": {"avg_answer_marks": 8, "total_rows": 2}}}
    store.write("1", summary, [])
    store.rename_group(gid, "New")
    kept = store.list_versions()[0]
    assert kept["group_names"] == ["New"] and "New" in kept["group_stats"] and kept["dataset"] == "New + Other"
    store.close()


@pytest.fixture
def client(tmp_path):
    cfg = Config(store_path=tmp_path / "api.json", require_login=False, eval_secret="s",
                 answer_weight=0.0, material_weight=1.0)
    with TestClient(create_app(cfg, fn=lambda q: "a")) as c:
        yield c


def test_api_recommendation_uses_serve_weights_and_skips_archived(client):
    store = client.app.state.store
    store.write("1", run(1, 9, 5, 1), [])
    store.write("2", run(2, 7, 9, 1), [])
    reco = client.get("/api/recommendation", params={"tolerance": 0}).json()
    assert reco["best"] == "2"                            # serve(material_weight=1.0) is honoured
    assert reco["weights"] == {"answer": 0.0, "material": 1.0}
    client.patch("/api/runs/2/archive")
    assert client.get("/api/recommendation").json()["best"] == "1"
    assert client.get("/api/recommendation", params={"tolerance": -1}).status_code == 422


def test_api_groups_list_has_last_and_best_and_test_cases_delete_for_good(client):
    gid = client.post("/api/groups", json={"name": "G"}).json()["group_id"]
    tc = client.post("/api/test-cases", json={
        "chat_id": "c", "turn_no": 1, "question": "q", "expected_answer": "a", "group_id": gid,
    }).json()
    stats = {"G": {"avg_answer_marks": 8, "avg_material_marks": 8, "avg_total_time": 1, "total_rows": 1}}
    client.app.state.store.write("1", run(1, 5, 5, 1, groups=stats), [])
    listed = client.get("/api/groups").json()[0]
    assert listed["last_run"]["version"] == "1" and listed["best_run"]["version"] == "1" and listed["run_count"] == 1
    history = client.get(f"/api/groups/{gid}/runs").json()
    assert history["best"]["version"] == "1" and len(history["runs"]) == 1
    assert client.delete(f"/api/test-cases/{tc['tc_id']}").status_code == 200
    assert client.delete(f"/api/test-cases/{tc['tc_id']}").status_code == 404
    assert client.get("/api/test-cases").json() == []
    assert client.post("/api/test-cases/status", json={"tc_ids": [], "status": "deleted"}).status_code == 422
