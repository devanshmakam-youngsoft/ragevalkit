"""A run writes its own log file, and what goes wrong is reported in plain words with the technical text kept apart."""
import time
from types import SimpleNamespace

import pandas as pd
import pytest

from ragevalkit.config import Config
from ragevalkit.evaluation.runner import RunManager
from ragevalkit.storage.store import EvalStore


@pytest.fixture
def config(tmp_path):
    return Config(store_path=tmp_path / "eval_store.json", run_semantic_similarity=False, run_bm25=False)


@pytest.fixture
def store(config):
    s = EvalStore(config.store_path)
    yield s
    s.close()


def _questions(count):
    return pd.DataFrame(
        [(f"c{n}", 1, "rag", f"question {n}", f"answer {n}") for n in range(count)],
        columns=["chat_id", "turn_no", "type", "question", "expected_answer"],
    )


def _finished(manager, df):
    run = manager.start("v1", df, "test set")
    deadline = time.time() + 20
    while run.status == "running" and time.time() < deadline:
        time.sleep(0.05)
    return run


def _manager(config, store, fn):
    manager = RunManager(config, store, fn, judge_fn=lambda q, e, g, m: {"answer_marks": 8})
    manager._llm_judge = SimpleNamespace(summarize_run=lambda stats: None)       # no model is called in tests
    return manager


def test_a_run_writes_a_log_file_beside_the_store(config, store):
    run = _finished(_manager(config, store, lambda question: "an answer"), _questions(2))
    assert run.status == "completed"
    log_files = list((config.logs_dir / "runs").glob("*_v1.log"))
    assert len(log_files) == 1 and config.logs_dir.parent == config.store_path.parent
    text = log_files[0].read_text(encoding="utf-8")
    assert "Run v1 started: 2 questions" in text and "Question 2 of 2" in text
    assert store.get("v1")["summary"]["log_file"] == log_files[0].name


def test_a_failing_chatbot_is_reported_once_in_plain_words_with_the_technical_text_on_request(config, store):
    def chatbot(question):
        raise ConnectionError("Connection refused by host 10.0.0.5 (api_key=abc123456789)")

    run = _finished(_manager(config, store, chatbot), _questions(3))
    assert run.status == "completed"
    summary = store.get("v1")["summary"]
    issue = next(i for i in summary["issues"] if i["stage"] == "answer")      # three questions, one cause, listed once
    assert len([i for i in summary["issues"] if i["stage"] == "answer"]) == 1
    assert issue["count"] == 3 and issue["stage"] == "answer"
    assert "could not be reached" in issue["message"] and "ConnectionError" not in issue["message"]
    assert "ConnectionError" in issue["technical"] and "abc123456789" not in issue["technical"]
    row = store.get("v1")["rows"][0]
    assert row["status"] == "generation_failed" and "ConnectionError" not in row["error_message"]
    assert "ConnectionError" in row["error_detail"]
    assert "Traceback" in next((config.logs_dir / "runs").glob("*_v1.log")).read_text(encoding="utf-8")


def test_the_issue_count_is_part_of_the_run_state_and_the_details_are_kept_apart(config, store):
    run = _finished(_manager(config, store, lambda question: 1 / 0), _questions(1))
    assert run.snapshot()["issue_count"] == run.log.issue_total >= 1
    first = run.log.issue_dicts()[0]
    assert first["technical"].startswith("Traceback") and "ZeroDivisionError" not in first["message"]


def test_a_log_folder_that_cannot_be_written_never_stops_the_run(config, store, tmp_path):
    blocker = tmp_path / "not_a_folder"
    blocker.write_text("a file where the log folder should be")
    config.log_dir = blocker
    run = _finished(_manager(config, store, lambda question: "an answer"), _questions(1))
    assert run.status == "completed" and store.get("v1")["summary"]["log_file"] is None
