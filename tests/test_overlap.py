"""Overlapping groups, run-time group labels on results, and the pitfalls / suggestions summary."""
import json
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from ragevalkit.config import Config
from ragevalkit.judge import Judge, parse_insights
from ragevalkit.server import create_app
from ragevalkit.store import EvalStore, build_group_stats


@pytest.fixture
def store(tmp_path):
    s = EvalStore(tmp_path / "store.json")
    yield s
    s.close()


def _df(rows):
    return pd.DataFrame(rows, columns=["chat_id", "turn_no", "type", "question", "expected_answer"])


def _overlapping(store):
    """q1 is only in A, q2 is in A and B, q3 is only in B."""
    a, b = store.create_group("A"), store.create_group("B")
    store.import_into_group(a, _df([("c1", 1, "rag", "q1", "x"), ("c2", 1, "rag", "q2", "x")]))
    store.import_into_group(b, _df([("c2", 1, "rag", "q2", "x"), ("c3", 1, "rag", "q3", "x")]))
    return a, b


def _rows(selection, marks):
    out = []
    for r in selection.df.itertuples(index=False):
        out.append({
            "chat_id": r.chat_id, "turn_no": r.turn_no, "question": r.question, "status": "ok", "tc_id": r.tc_id,
            "groups": list(r.groups), "answer_marks": marks[r.question], "material_marks": 5,
            "total_time_taken": 1.0,
        })
    return out


def test_each_row_records_the_groups_it_belonged_to_when_it_ran(store):
    a, b = _overlapping(store)
    sel = store.resolve_selection(group_ids=[a, b])
    assert {r.question: list(r.groups) for r in sel.df.itertuples(index=False)} == {
        "q1": ["A"], "q2": ["A", "B"], "q3": ["B"],
    }


def test_group_scores_count_an_overlapping_case_in_each_of_its_groups_but_once_overall(store):
    a, b = _overlapping(store)
    sel = store.resolve_selection(group_ids=[a, b])
    assert sel.total == 3                                            # q2 runs once
    rows = _rows(sel, {"q1": 10, "q2": 6, "q3": 2})
    stats = build_group_stats(store, sel.group_names, rows)
    assert stats["A"]["total_rows"] == 2 and stats["A"]["avg_answer_marks"] == 8.0     # q1 + q2
    assert stats["B"]["total_rows"] == 2 and stats["B"]["avg_answer_marks"] == 4.0     # q2 + q3


def test_group_scores_follow_labels_at_run_time_not_the_library_afterwards(store):
    a, b = _overlapping(store)
    sel = store.resolve_selection(group_ids=[a])
    rows = _rows(sel, {"q1": 10, "q2": 6})
    cases = {c["question"]: c["tc_id"] for c in store.list_test_cases()}
    store.set_test_case_groups(cases["q1"], [])                      # relabelled after the run
    assert build_group_stats(store, ["A"], rows)["A"]["total_rows"] == 2


def test_old_results_without_saved_labels_are_labelled_when_read(store):
    a, _ = _overlapping(store)
    store.write("1", {"version": "1", "date": "2026-01-01T00:00:00+00:00"},
                [{"chat_id": "c1", "turn_no": 1, "question": "q1", "status": "ok"}])
    assert store.get("1")["rows"][0]["groups"] == ["A"]


def test_the_excel_export_has_a_groups_column(store):
    a, b = _overlapping(store)
    sel = store.resolve_selection(group_ids=[a, b])
    store.write("1", {"version": "1", "date": "2026-01-01T00:00:00+00:00"}, _rows(sel, {"q1": 1, "q2": 2, "q3": 3}))
    import io
    import openpyxl
    book = openpyxl.load_workbook(io.BytesIO(store.export_xlsx("1")))
    sheet = book["Results"]
    header = [c.value for c in sheet[1]]
    col = header.index("groups")
    assert {sheet.cell(row=i, column=col + 1).value for i in range(2, 5)} == {"A", "A, B", "B"}


# ---- pitfalls & suggestions --------------------------------------------------

def test_parse_insights_accepts_clean_fenced_and_chatty_replies():
    clean = json.dumps({"pitfalls": ["Slow retrieval."], "suggestions": ["Cache it."]})
    assert parse_insights(clean) == {"pitfalls": ["Slow retrieval."], "suggestions": ["Cache it."]}
    assert parse_insights(f"```json\n{clean}\n```")["suggestions"] == ["Cache it."]
    assert parse_insights(f"Here you go: {clean} Hope that helps")["pitfalls"] == ["Slow retrieval."]
    assert parse_insights(json.dumps({"pitfalls": "- one thing", "suggestions": []}))["pitfalls"] == ["one thing"]


@pytest.mark.parametrize("raw", ["", "not json", "[1, 2]", json.dumps({"pitfalls": [], "suggestions": []}), None])
def test_parse_insights_rejects_replies_with_nothing_usable(raw):
    assert parse_insights(raw) is None


def test_summarize_run_returns_bullets_retries_bad_replies_and_gives_up_cleanly(monkeypatch):
    monkeypatch.setattr("ragevalkit.judge.time.sleep", lambda s: None)
    judge = Judge(SimpleNamespace(judge_prompt_override="", judge_retries=2, summary_prompt=""))
    replies = iter(["garbage", json.dumps({"pitfalls": ["a"], "suggestions": ["b"]})])
    sent = []
    judge._call = lambda messages, json_mode=False: (sent.append(messages), next(replies))[1]
    assert judge.summarize_run("stats") == {"pitfalls": ["a"], "suggestions": ["b"]}
    assert '"pitfalls"' in sent[0][0]["content"] and "do NOT restate" in sent[0][0]["content"]

    judge._call = lambda messages, json_mode=False: "still garbage"
    assert judge.summarize_run("stats") is None


def test_a_custom_summary_prompt_still_gets_the_json_format_appended():
    judge = Judge(SimpleNamespace(judge_prompt_override="", judge_retries=1, summary_prompt="Focus on speed."))
    seen = {}
    judge._call = lambda messages, json_mode=False: (seen.update(system=messages[0]["content"]), '{"pitfalls": ["x"]}')[1]
    judge.summarize_run("stats")
    assert seen["system"].startswith("Focus on speed.") and '"pitfalls"' in seen["system"]
