"""Versions are compared on the test cases they share, not on whole-run averages."""
import pytest
from fastapi.testclient import TestClient

from ragevalkit.api import create_app
from ragevalkit.config import Config
from ragevalkit.recommendation.engine import recommend
from ragevalkit.recommendation.group_overview import group_overview
from ragevalkit.run_summary.case_scores import build_case_scores, case_key
from ragevalkit.storage.store import EvalStore


def entry(key, answer, material=8.0, time=1.0, ok=True, groups=()):
    return {"k": key, "a": answer, "m": material, "t": time, "ok": ok, "g": list(groups)}


def version(n, entries, **extra):
    return {"version": str(n), "date": f"2026-01-{n:02d}T00:00:00+00:00", "case_scores": entries, **extra}


def cases(prefix, count, answer=9.0, **kw):
    return [entry(f"{prefix}{i}", answer, **kw) for i in range(count)]


CORE = lambda answer=9.0, **kw: cases("c", 10, answer, **kw)


def test_a_version_that_ran_extra_cases_is_compared_on_the_ones_it_shares():
    # v1-v3 ran the 10 core cases; v4 also ran an extra group. It is judged on the 10 core cases only.
    v4 = CORE(7.0) + cases("m", 9, answer=1.0)
    result = recommend([version(1, CORE(9.0)), version(2, CORE(9.0)), version(3, CORE(9.0)), version(4, v4)], tolerance=0.1)
    assert result["not_comparable"] == []
    assert result["compared_cases"] == 10
    assert result["scores"]["4"]["answer"] == 7.0          # not dragged down to ~4 by the 9 extra cases
    assert result["partial"] == [{"version": "4", "ran": 19, "compared": 10}]
    assert result["best"] in {"1", "2", "3"}


def test_adding_a_test_case_to_a_group_does_not_hide_the_next_version():
    # the reported case: core ran 10 cases in v1-3 and 11 in v4 (one added)
    core = lambda n, a: cases("c", n, a, groups=["core"])
    result = recommend([version(1, core(10, 9.0)), version(2, core(10, 9.2)), version(3, core(10, 9.1)), version(4, core(11, 8.0))],
                       group="core")
    assert result["not_comparable"] == [] and result["compared_cases"] == 10
    assert result["best"] == "2"                           # highest overall score; v4 (8.0) is outside the tie margin
    assert set(result["scores"]) == {"1", "2", "3", "4"}
    assert result["scores"]["4"]["answer"] == 8.0


def test_a_tiny_smoke_run_cannot_shrink_everyones_comparison():
    result = recommend([version(1, CORE()), version(2, CORE()), version(3, CORE()), version(4, cases("c", 2))])
    assert result["not_comparable"] == ["4"] and result["compared_cases"] == 10
    assert "shares only 2" in result["not_comparable_detail"]["4"]


def test_a_version_that_ran_entirely_different_cases_is_not_compared():
    result = recommend([version(1, CORE()), version(2, CORE()), version(3, cases("other", 10))])
    assert result["not_comparable"] == ["3"] and result["compared_cases"] == 10


def test_a_case_whose_question_or_expected_answer_changed_is_not_treated_as_the_same_case():
    old = [entry(case_key("c", 1, f"q{i}", "a"), 9.0) for i in range(10)]
    edited = [entry(case_key("c", 1, f"q{i}", "a" if i else "a CHANGED"), 9.0) for i in range(10)]
    result = recommend([version(1, old), version(2, edited)])
    assert result["compared_cases"] == 9


def test_a_failure_on_a_shared_case_excludes_the_version_but_one_elsewhere_does_not():
    bad_shared = CORE() ; bad_shared[0] = entry("c0", 0.0, ok=False)
    extra_failure = CORE() + [entry("extra", 0.0, ok=False)]
    result = recommend([version(1, CORE()), version(2, bad_shared)])
    assert result["excluded"] == ["2"] and "failed" in result["excluded_detail"]["2"] and result["best"] == "1"
    result = recommend([version(1, CORE()), version(2, extra_failure)])
    assert result["excluded"] == [] and set(result["scores"]) == {"1", "2"}


def test_stopped_runs_are_left_out():
    result = recommend([version(1, CORE()), version(2, CORE(10.0), stopped=True)])
    assert result["excluded"] == ["2"] and result["best"] == "1"


def test_context_quality_is_only_counted_when_every_compared_version_has_it():
    result = recommend([version(1, CORE(9.0, material=9.0)), version(2, CORE(8.5, material=None))])
    assert result["basis"] == "answer_only" and "v2" in result["basis_note"]
    assert recommend([version(1, CORE(9.0, material=9.0)), version(2, CORE(8.5, material=6.0))])["basis"] == "weighted"


def test_the_overall_score_and_speed_tie_break_still_decide_between_compared_versions():
    slow = CORE(9.5, time=4.0)
    fast = CORE(9.4, time=2.0)
    assert recommend([version(1, slow), version(2, fast)], tolerance=0.25)["best"] == "2"
    assert recommend([version(1, slow), version(2, fast)], tolerance=0.01)["best"] == "1"


def test_group_overview_lists_each_run_and_uses_the_shared_cases_for_best():
    core = lambda n, a: cases("c", n, a, groups=["core"])
    versions = [version(1, core(10, 9.0)), version(2, core(11, 9.6)), version(3, core(10, 7.0))]
    overview = group_overview(versions, "core", tolerance=0.05)
    assert [h["version"] for h in overview["runs"]] == ["3", "2", "1"]
    assert overview["runs"][1]["total_rows"] == 11            # what the group did in that run
    assert overview["best"]["version"] == "2" and overview["compared_cases"] == 10


# ---- saving and reading per-case scores ------------------------------------------------------

def test_case_scores_are_saved_compactly_with_run_time_groups():
    rows = [{"chat_id": "c", "turn_no": 1, "question": "q", "expected_answer": "a", "answer_marks": 8,
             "material_marks": None, "total_time_taken": 1.5, "status": "ok", "groups": ["G"]},
            {"chat_id": "c", "turn_no": 2, "question": "q2", "expected_answer": "a", "status": "generation_failed"}]
    first, second = build_case_scores(rows)
    assert first == {"k": case_key("c", 1, "q", "a"), "a": 8, "m": None, "t": 1.5, "ok": True, "g": ["G"]}
    assert second["ok"] is False and second["a"] is None
    assert case_key("c", 1, "q", "a") != case_key("c", 1, "q", "different")


@pytest.fixture
def client(tmp_path):
    cfg = Config(store_path=tmp_path / "api.json", require_login=False, eval_secret="s")
    with TestClient(create_app(cfg, fn=lambda q: "a")) as c:
        yield c


def test_older_runs_are_filled_in_from_their_results_and_the_big_list_stays_out_of_the_api(client):
    store: EvalStore = client.app.state.store
    rows = [{"chat_id": "c", "turn_no": i, "question": f"q{i}", "expected_answer": "a", "answer_marks": 9, "material_marks": 8,
             "total_time_taken": 1.0, "status": "ok"} for i in range(1, 4)]
    summary = {"version": "1", "date": "2026-01-01T00:00:00+00:00", "total_rows": 3, "failed_rows": 0,
               "avg_answer_marks": 9, "avg_material_marks": 8, "avg_total_time": 1.0}
    store.write("1", summary, rows)                          # a run saved before per-case scores existed
    assert "case_scores" not in store.runs.all()[0]
    full = store.list_versions_for_comparison()
    assert len(full[0]["case_scores"]) == 3 and "case_scores" in store.runs.all()[0]   # backfilled once, then kept
    assert "case_scores" not in client.get("/api/versions").json()[0]
    assert "case_scores" not in client.get("/api/versions/1").json()["summary"]
    assert client.get("/api/recommendation").json()["compared_cases"] == 3
