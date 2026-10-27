"""Overlapping groups, run-time group labels on results, and the pitfalls / suggestions summary."""
import json
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from ragevalkit.config import Config
from ragevalkit.judging.judge import Judge
from ragevalkit.judging.insights import parse_insights
from ragevalkit.server import create_app
from ragevalkit.storage.store import EvalStore
from ragevalkit.run_summary.group_stats import build_group_stats


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
    monkeypatch.setattr("ragevalkit.judging.judge.time.sleep", lambda s: None)
    judge = Judge(SimpleNamespace(judge_prompt_override="", judge_retries=2, summary_prompt=""))
    replies = iter(["garbage", json.dumps({"pitfalls": ["a"], "suggestions": ["b"]})])
    sent = []
    judge._call = lambda messages, json_mode=False: (sent.append(messages), next(replies))[1]
    assert judge.summarize_run("stats") == {"pitfalls": ["a"], "suggestions": ["b"], "items": [{"watch_out": "a", "suggestion": "b"}]}
    assert '"items"' in sent[0][0]["content"] and "do NOT restate" in sent[0][0]["content"]

    judge._call = lambda messages, json_mode=False: "still garbage"
    assert judge.summarize_run("stats") is None


def test_a_custom_summary_prompt_still_gets_the_json_format_appended():
    judge = Judge(SimpleNamespace(judge_prompt_override="", judge_retries=1, summary_prompt="Focus on speed."))
    seen = {}
    judge._call = lambda messages, json_mode=False: (seen.update(system=messages[0]["content"]), '{"pitfalls": ["x"]}')[1]
    judge.summarize_run("stats")
    assert seen["system"].startswith("Focus on speed.") and '"items"' in seen["system"]


# ---- summaries that must have both lists -------------------------------------------------------------------

def make_judge(retries=3):
    return Judge(SimpleNamespace(judge_prompt_override="", judge_retries=retries, summary_prompt=""))


def test_a_summary_without_suggestions_is_sent_back_with_the_reason_until_it_has_them(monkeypatch):
    monkeypatch.setattr("ragevalkit.judging.judge.time.sleep", lambda s: None)
    judge = make_judge()
    replies = iter([json.dumps({"pitfalls": ["Slow search."], "suggestions": []}),
                    json.dumps({"pitfalls": ["Slow search."], "suggestions": ["Check the search index."]})])
    sent = []
    judge._call = lambda messages, json_mode=False: (sent.append(messages), next(replies))[1]
    assert judge.summarize_run("stats") == {"pitfalls": ["Slow search."], "suggestions": ["Check the search index."],
                                            "items": [{"watch_out": "Slow search.", "suggestion": "Check the search index."}]}
    assert len(sent) == 2
    feedback = sent[1][-1]["content"]
    assert sent[1][-2]["role"] == "assistant" and '"suggestions" was empty' in feedback and "for each watch-out" in feedback


def test_when_the_model_never_gives_suggestions_what_it_did_give_is_kept(monkeypatch):
    monkeypatch.setattr("ragevalkit.judging.judge.time.sleep", lambda s: None)
    judge = make_judge(retries=2)
    judge._call = lambda messages, json_mode=False: json.dumps({"pitfalls": ["Slow search."]})
    assert judge.summarize_run("stats") == {"pitfalls": ["Slow search."], "suggestions": []}      # the runner fills the gap


def test_a_failing_call_is_retried_then_the_summary_gives_up_cleanly(monkeypatch):
    monkeypatch.setattr("ragevalkit.judging.judge.time.sleep", lambda s: None)
    judge = make_judge(retries=2)
    calls = []

    def boom(messages, json_mode=False):
        calls.append(1)
        raise ConnectionError("network down")

    judge._call = boom
    assert judge.summarize_run("stats") is None and len(calls) == 2


PAIR = {"pitfalls": ["a slow step"], "suggestions": ["speed it up"], "items": [{"watch_out": "a slow step", "suggestion": "speed it up"}]}


@pytest.mark.parametrize("reply, expected", [
    ({"watch_outs": ["a slow step"], "recommendations": ["speed it up"]}, PAIR),
    ({"Pitfalls": [{"text": "a slow step"}], "Next Steps": [{"title": "speed it up", "detail": "x"}]}, PAIR),
    ({"pitfalls": ["a slow step", "a slow step", "None."], "suggestions": "- speed it up"}, PAIR),
])
def test_summary_replies_are_read_whatever_names_and_shapes_the_model_used(reply, expected):
    from ragevalkit.judging.insights import check_insights
    found, problem = check_insights(json.dumps(reply))
    assert problem == "" and found == expected


def test_the_summary_prompt_asks_for_actions_never_empty_and_no_jargon():
    from ragevalkit.judging.prompts import run_summary_format, run_summary_prompt
    text = run_summary_prompt + run_summary_format
    for needle in ("do NOT restate", "never empty", "starting with a verb", "no jargon", "every item needs both parts", "THAT watch-out",
                   "Never write BM25", "Example of one finding"):
        assert needle in text


def test_suggestions_read_from_the_numbers_are_never_empty_and_fit_the_run():
    from ragevalkit.judging.fallback_insights import default_suggestions
    clean = {"failed_rows": 0, "avg_material_marks": 9.5, "avg_total_time": 2.0, "scores": {"tiers": {"low": 0}}}
    assert default_suggestions(clean, []) == ["Keep this version as the baseline and add harder test cases (indirect and multi-turn questions) to find where it breaks."]
    troubled = {"failed_rows": 2, "avg_material_marks": 5.0, "avg_total_time": 4.0, "avg_retrieval": 3.0, "avg_llm": 0.5,
                "scores": {"tiers": {"low": 3}, "sources": {"checked": 4, "matched": 2}}}
    out = default_suggestions(troubled, [])
    assert len(out) == 3 and out[0].startswith("Open the 2 failed questions") and any("weak answers" in t for t in out)
    slow = default_suggestions({"failed_rows": 0, "avg_material_marks": 9, "avg_total_time": 4.0, "avg_retrieval": 3.0, "avg_llm": 0.5, "scores": {}}, [])
    assert slow == ["Retrieval takes 75% of the response time: start there to make answers faster."]


def test_the_model_is_told_each_steps_share_of_the_response_time():
    from ragevalkit.judging.run_summary_input import stats_for_llm
    summary = {"total_rows": 2, "failed_rows": 0, "avg_answer_marks": 9, "avg_material_marks": 9, "avg_keyword_recall": 0.5,
               "avg_semantic_similarity": 0.5, "avg_total_time": 4.0, "avg_retrieval": 3.0, "scores": {}}
    assert "retrieval=3.0s (75% of the response time)" in stats_for_llm(summary, [])


# ---- every watch-out paired with the suggestion that answers it ----------------------------------------------

PAIRED = {"items": [{"watch_out": "The multi-turn group scores lowest.", "suggestion": "Pass the earlier answer into each follow-up."},
                    {"watch_out": "Finding documents takes most of the time.", "suggestion": "Check why the document search is slow."}]}


def test_paired_findings_are_accepted_and_keep_their_pairing():
    from ragevalkit.judging.insights import check_insights
    found, problem = check_insights(json.dumps(PAIRED))
    assert problem == "" and found["items"] == PAIRED["items"]
    assert found["pitfalls"] == [i["watch_out"] for i in PAIRED["items"]] and found["suggestions"] == [i["suggestion"] for i in PAIRED["items"]]


def test_a_finding_without_its_suggestion_is_sent_back_naming_the_item(monkeypatch):
    monkeypatch.setattr("ragevalkit.judging.judge.time.sleep", lambda s: None)
    judge = make_judge()
    broken = {"items": [PAIRED["items"][0], {"watch_out": "Finding documents takes most of the time.", "suggestion": ""}]}
    replies = iter([json.dumps(broken), json.dumps(PAIRED)])
    sent = []
    judge._call = lambda messages, json_mode=False: (sent.append(messages), next(replies))[1]
    assert judge.summarize_run("stats")["items"] == PAIRED["items"]
    assert 'item 2 has no "suggestion"' in sent[1][-1]["content"]


def test_unequal_parallel_lists_are_asked_to_use_the_paired_shape():
    from ragevalkit.judging.insights import check_insights
    found, problem = check_insights(json.dumps({"pitfalls": ["a", "b"], "suggestions": ["c"]}))
    assert found is None and '"items"' in problem and "its own suggestion" in problem


def test_a_watch_out_left_without_a_suggestion_gets_one_from_the_numbers():
    from ragevalkit.judging.fallback_insights import finish_insights
    summary = {"failed_rows": 2, "avg_material_marks": 9, "avg_total_time": 2.0, "scores": {"tiers": {"low": 0}}}
    half = {"items": [{"watch_out": "Some questions failed.", "suggestion": ""}, {"watch_out": "Slow.", "suggestion": "Look at the slowest step."}],
            "pitfalls": ["Some questions failed.", "Slow."], "suggestions": ["Look at the slowest step."]}
    done = finish_insights(half, summary, [])
    assert done["items"][0]["suggestion"].startswith("Open the 2 failed questions") and done["items"][1]["suggestion"] == "Look at the slowest step."
    assert len(done["pitfalls"]) == len(done["suggestions"]) == 2


def test_older_style_lists_are_paired_by_position_and_never_left_blank():
    from ragevalkit.judging.fallback_insights import finish_insights
    done = finish_insights({"pitfalls": ["One.", "Two."], "suggestions": ["Fix one."]}, {"failed_rows": 0, "scores": {}}, [])
    assert done["items"][0] == {"watch_out": "One.", "suggestion": "Fix one."}
    assert done["items"][1]["watch_out"] == "Two." and done["items"][1]["suggestion"]


def test_the_model_is_told_the_figures_in_plain_words():
    from ragevalkit.judging.run_summary_input import stats_for_llm
    text = stats_for_llm({"total_rows": 1, "failed_rows": 0, "avg_answer_marks": 9, "avg_material_marks": 9, "avg_keyword_recall": 0.5,
                          "avg_semantic_similarity": 0.4, "avg_total_time": 2.0, "scores": {}}, [])
    assert "semantic" not in text.lower() and "recall" not in text.lower() and "meaning match" in text and "Step names" in text
