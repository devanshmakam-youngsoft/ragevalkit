"""The recommendation says when nothing is good enough, what it could not compare, and how the latest run changed it."""
import pandas as pd
import pytest

from ragevalkit.recommendation.engine import recommend
from ragevalkit.storage.store import EvalStore


def entry(key, answer, material=None, time=1.0):
    return {"k": key, "a": answer, "m": material if material is not None else answer, "t": time, "ok": True, "g": []}


def version(n, entries):
    return {"version": str(n), "date": f"2026-01-{n:02d}T00:00:00+00:00", "case_scores": entries}


def cases(prefix, count, answer, **kw):
    return [entry(f"{prefix}{i}", answer, **kw) for i in range(count)]


def test_a_version_that_gets_everything_wrong_is_not_recommended_but_is_named_the_best_so_far():
    result = recommend([version(1, cases("c", 5, 0.0, time=0.02)), version(2, cases("c", 5, 0.0, time=7.0))])
    assert result["best"] is None and result["below_minimum"] is True
    assert result["best_so_far"] == {"version": "1", "quality": 0.0}
    assert "best so far" in result["reason"] and result["min_quality"] == 5.0


def test_the_bar_can_be_changed_or_removed():
    versions = [version(1, cases("c", 5, 3.0))]
    assert recommend(versions)["best"] is None
    assert recommend(versions, min_quality=2.0)["best"] == "1"
    assert recommend(versions, min_quality=0)["best"] == "1"


def test_a_good_version_on_different_test_cases_is_shown_not_hidden():
    # the reported case: v1 and v2 ran 5 cases and scored 0; v3 ran 2 other cases and scored 10
    result = recommend([version(1, cases("old", 5, 0.0)), version(2, cases("old", 5, 0.0)), version(3, cases("new", 2, 10.0))])
    assert result["not_comparable"] == ["3"]
    assert result["not_comparable_scores"]["3"] == {"answer": 10.0, "material": 10.0, "time": 1.0, "cases": 2}
    assert result["best"] is None and result["best_so_far"]["version"] in {"1", "2"}


def test_the_latest_run_is_compared_with_the_recommended_one():
    result = recommend([version(1, cases("c", 5, 9.0, time=1.0)), version(2, cases("c", 5, 8.0, time=3.0))], tolerance=0.1)
    assert result["best"] == "1"
    assert result["latest_vs_best"] == {"version": "2", "answer": -1.0, "material": -1.0, "time": 2.0, "quality": -1.0}


def test_there_is_no_comparison_when_the_latest_run_is_the_recommended_one():
    result = recommend([version(1, cases("c", 5, 6.0)), version(2, cases("c", 5, 9.0))])
    assert result["best"] == "2" and result["latest_vs_best"] is None


def test_it_says_what_was_recommended_before_the_latest_run():
    versions = [version(1, cases("c", 5, 6.0)), version(2, cases("c", 5, 8.0)), version(3, cases("c", 5, 9.5))]
    result = recommend(versions)
    assert result["best"] == "3" and result["previous_best"] == "2"
    assert recommend(versions[:1])["previous_best"] is None


def test_a_run_is_labelled_with_the_groups_that_had_test_cases_in_it(tmp_path):
    store = EvalStore(tmp_path / "store.json")
    try:
        full, empty = store.create_group("Direct"), store.create_group("Multi-turn")
        store.import_into_group(full, pd.DataFrame([("c1", 1, "rag", "q", "a")], columns=["chat_id", "turn_no", "type", "question", "expected_answer"]))
        selection = store.resolve_selection([full, empty])
        assert selection.group_names == ["Direct"] and selection.total == 1
    finally:
        store.close()


@pytest.mark.parametrize("answer,expected", [(4.9, None), (5.0, "1")])
def test_the_default_bar_is_five_out_of_ten(answer, expected):
    assert recommend([version(1, cases("c", 3, answer))])["best"] == expected
