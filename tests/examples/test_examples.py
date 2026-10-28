"""The files in examples/ are what the guide shows, so each one is run for real: served the way `python file.py` would
serve it, then driven through a run, and what the dashboard would show is checked."""
import json
import runpy
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
import uvicorn
from fastapi.testclient import TestClient

from ragevalkit.api import create_app
from ragevalkit.config import Config

EXAMPLES = Path(__file__).parents[2] / "examples"
COLUMNS = ["chat_id", "turn_no", "type", "question", "expected_answer"]
JUDGE = lambda question, expected, generated, material: {"answer_marks": 8, "material_marks": 8}   # noqa: E731


@pytest.fixture
def serve_example(tmp_path, monkeypatch):
    """Run an example file as a script, but catch the app it would serve instead of starting a server."""
    monkeypatch.chdir(tmp_path)
    caught = {}
    monkeypatch.setattr("uvicorn.run", lambda app, **options: caught.update(app=app))
    monkeypatch.setattr("ragevalkit.launcher.configure_logging", lambda config: None)
    monkeypatch.setattr("ragevalkit.launcher.llm.load_litellm", lambda: None)
    monkeypatch.setattr("ragevalkit.metrics.semantic_similarity", lambda *args, **options: 0.5)   # no model download
    monkeypatch.setattr("ragevalkit.launcher.threading.Timer", lambda *args, **options: SimpleNamespace(start=lambda: None))

    def serve(name, fake_judge=True):
        runpy.run_path(str(EXAMPLES / name), run_name="__main__")
        app = caught["app"]
        if fake_judge:                                  # no model is called: an example's own judge_fn is kept
            app.state.manager._judge_fn = app.state.manager._judge_fn or JUDGE
            app.state.manager._llm_judge = SimpleNamespace(summarize_run=lambda stats: None)
        return app

    yield serve
    if "app" in caught:
        caught["app"].state.store.close()


@pytest.fixture
def served_function(tmp_path):
    """An app serving a function that is defined in an example file."""
    apps = []

    def build(fn, config_options=None, **options):
        config = Config(store_path=tmp_path / f"store{len(apps)}.json", require_login=False,
                        run_semantic_similarity=False, run_bm25=False, **(config_options or {}))
        app = create_app(config, fn=fn, judge_fn=options.pop("judge_fn", JUDGE), **options)
        app.state.manager._llm_judge = SimpleNamespace(summarize_run=lambda stats: None)
        apps.append(app)
        return app

    yield build
    for app in apps:
        app.state.store.close()


def evaluate(app, questions, case_type="rag", extra=None) -> list[dict]:
    """Run (chat_id, turn_no, question, expected) rows and return the saved result rows."""
    frame = pd.DataFrame([(chat, turn, case_type, question, expected) for chat, turn, question, expected in questions], columns=COLUMNS)
    for name, values in (extra or {}).items():
        frame[name] = values
    run = app.state.manager.start("v1", frame, "example")
    deadline = time.time() + 30
    while run.status == "running" and time.time() < deadline:
        time.sleep(0.05)
    assert run.status == "completed", run.error
    return app.state.store.get("v1")["rows"]


def steps_of(row: dict) -> list[str]:
    return list(row["node_timings"])


# ---- function_shapes.py -----------------------------------------------------------------------------------------

def test_function_shapes_example_is_served(serve_example):
    app = serve_example("function_shapes.py")
    rows = evaluate(app, [("c1", 1, "Can I get a refund?", "30 days"), ("c1", 2, "And for annual plans?", "pro rata")])
    assert "Following up on 'Can I get a refund?'" in rows[1]["generated_answer"]


def test_each_of_the_three_shapes_works(served_function):
    shapes = runpy.run_path(str(EXAMPLES / "function_shapes.py"))
    only = evaluate(served_function(shapes["answer_only"]), [("c1", 1, "Refunds?", "30 days")])
    assert only[0]["status"] == "ok"

    history = evaluate(served_function(shapes["answer_with_history"]), [("c1", 1, "Refunds?", "x"), ("c1", 2, "Shipping?", "x")])
    assert "Following up" not in history[0]["generated_answer"] and "Following up on 'Refunds?'" in history[1]["generated_answer"]

    shapes["SESSIONS"].clear()
    session = evaluate(served_function(shapes["answer_in_session"]), [("c1", 1, "a?", "x"), ("c1", 2, "b?", "x"), ("c2", 1, "c?", "x")])
    assert [r["generated_answer"].split(".")[0] for r in session] == [
        "This is message 1 of this chat", "This is message 2 of this chat", "This is message 1 of this chat"]


def test_dict_async_and_renamed_parameters_are_understood(served_function):
    shapes = runpy.run_path(str(EXAMPLES / "function_shapes.py"))
    chat = [("c1", 1, "Refunds?", "x"), ("c1", 2, "And shipping?", "x")]
    assert evaluate(served_function(shapes["answer_as_dict"]), chat[:1])[0]["generated_answer"].startswith("Refunds are allowed")
    assert evaluate(served_function(shapes["answer_async"]), chat[:1])[0]["generated_answer"].startswith("Refunds are allowed")
    renamed = served_function(shapes["answer_with_other_names"], config_options={"history_params": ["past_chats"]})
    assert evaluate(renamed, chat)[1]["generated_answer"] == "I can see 1 earlier turns."
    openai = served_function(shapes["answer_with_openai_history"], config_options={"history_format": "openai"})
    assert [r["generated_answer"] for r in evaluate(openai, chat)] == ["This is the first question.", "Earlier you said: Refunds?"]


# ---- steps_two_ways.py ------------------------------------------------------------------------------------------

def test_the_two_step_styles_record_the_same_steps_and_the_same_material(served_function):
    module = runpy.run_path(str(EXAMPLES / "steps_two_ways.py"))
    question = [("c1", 1, "Can I get a refund?", "30 days")]
    blocks = evaluate(served_function(module["pipeline_with_blocks"]), question)[0]
    decorated = evaluate(served_function(module["pipeline_with_decorators"]), question)[0]

    assert steps_of(blocks) == steps_of(decorated) == ["retrieval", "llm"]
    assert blocks["material"] == decorated["material"] == "Refunds are allowed within 30 days of purchase."
    assert blocks["generated_answer"] == decorated["generated_answer"]
    # the difference between them
    assert blocks["sources"] == ["refunds.pdf"] and decorated["sources"] == []
    assert decorated["step_inputs"]["retrieval"] == {"question": "Can I get a refund?"}
    assert decorated["step_outputs"]["retrieval"] == "Refunds are allowed within 30 days of purchase."
    assert blocks["step_inputs"]["retrieval"] == {} and blocks["step_outputs"]["retrieval"] == ""


def test_steps_two_ways_example_is_served(serve_example):
    rows = evaluate(serve_example("steps_two_ways.py"), [("c1", 1, "When do orders ship?", "2 business days")])
    assert rows[0]["sources"] == ["shipping.pdf"]


# ---- rag_pipeline.py --------------------------------------------------------------------------------------------

def test_rag_pipeline_only_the_search_declares_material(serve_example):
    rows = evaluate(serve_example("rag_pipeline.py"), [("c1", 1, "How long do refunds take?", "30 days")])
    row = rows[0]
    assert steps_of(row) == ["rewrite", "retrieval", "rerank", "llm"]
    assert "Refunds are allowed within 30 days" in row["material"] and "Orders ship" not in row["material"]
    assert row["sources"][0] == "refunds.pdf"
    assert row["flags"]["documents_found"] == "1"


# ---- langgraph_agent.py -----------------------------------------------------------------------------------------

def test_steps_inside_langgraph_nodes_are_recorded(serve_example):
    pytest.importorskip("langgraph")
    row = evaluate(serve_example("langgraph_agent.py"), [("c1", 1, "Can I get a refund?", "30 days")])[0]
    assert steps_of(row) == ["rewrite", "retrieval", "llm"]
    assert row["material"] == "Refunds are allowed within 30 days of purchase." and row["sources"] == ["refunds.pdf"]
    assert row["step_inputs"]["rewrite"] == {"question": "Can I get a refund?"}
    assert row["generated_answer"] == "Refunds are allowed within 30 days of purchase."


# ---- no_retrieval_bot.py ----------------------------------------------------------------------------------------

def test_a_bot_with_no_retrieval_is_graded_on_the_answer_alone(serve_example):
    app = serve_example("no_retrieval_bot.py")
    rows = evaluate(app, [("c1", 1, "Hello there", "greets"), ("c2", 1, "Where is order A100?", "shipped")], case_type="non-rag")
    assert [r["material_marks"] for r in rows] == [None, None] and [r["answer_marks"] for r in rows] == [8, 8]
    assert rows[1]["flags"] == {"intent": "order_status", "tool_called": "order_lookup"}
    assert steps_of(rows[1]) == ["intent", "order_lookup"] and rows[1]["generated_answer"] == "Order A100 is shipped."
    assert app.state.config.material_weight == 0


# ---- custom_judge.py and custom_judge_prompt.py -----------------------------------------------------------------

def test_a_custom_judge_function_replaces_the_ai_judge(serve_example):
    app = serve_example("custom_judge.py")
    assert app.state.manager._judge_fn.__name__ == "valid_json_with_fields"
    rows = evaluate(app, [("c1", 1, "Where is my order?", "status, eta"), ("c2", 1, "Where is my order?", "status, eta, carrier")])
    assert [r["answer_marks"] for r in rows] == [10, 7]
    assert "carrier" in rows[1]["answer_remarks"]


def test_the_other_judges_in_the_example_grade_as_described():
    judges = runpy.run_path(str(EXAMPLES / "custom_judge.py"))
    contains, both = judges["contains_expected_answer"], judges["grade_answer_and_context"]
    assert contains("q", "30 days", "Within 30 days.", "")["answer_marks"] == 10
    assert contains("q", "30 days", "Never.", "")["answer_marks"] == 0
    assert judges["valid_json_with_fields"]("q", "a", "not json", "")["answer_comment"] == "The reply is not valid JSON."
    graded = both("q", "30 days", "Within 30 days.", "Policy: 30 days.")
    assert (graded["answer_marks"], graded["material_marks"]) == (10, 10)


def test_a_custom_rubric_gets_the_reply_format_added(serve_example):
    app = serve_example("custom_judge_prompt.py", fake_judge=False)
    prompt = app.state.manager.judge._grader_prompt
    assert "customer-support assistant" in prompt and "Respond ONLY with a JSON object" in prompt
    assert app.state.config.summary_prompt.startswith("You are reviewing one test run") and app.state.config.judge_model == "openai/gpt-4o-mini"


# ---- metrics_and_hooks.py ---------------------------------------------------------------------------------------

def test_extra_metrics_columns_and_the_completion_hook(serve_example, capsys):
    app = serve_example("metrics_and_hooks.py")
    rows = evaluate(app, [("c1", 1, "Refunds?", "Refunds are allowed within 30 days")], extra={"difficulty": ["easy"]})
    assert rows[0]["word_overlap"] == 1.0 and rows[0]["length_ratio"] > 1 and rows[0]["difficulty"] == "easy"
    deadline = time.time() + 5
    while "answer quality" not in capsys.readouterr().out and time.time() < deadline:
        time.sleep(0.05)
    assert app.state.config.column_map == {"user_query": "question", "gold_answer": "expected_answer"}


# ---- call_existing_api.py ---------------------------------------------------------------------------------------

@pytest.fixture
def fake_bot():
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append(body)
            reply = json.dumps({"reply": f"echo: {body['message']}"}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(reply)))
            self.end_headers()
            self.wfile.write(reply)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/chat", received
    server.shutdown()


def test_an_already_deployed_bot_is_evaluated_over_http(serve_example, monkeypatch, fake_bot):
    url, received = fake_bot
    monkeypatch.setenv("BOT_URL", url)
    app = serve_example("call_existing_api.py")
    rows = evaluate(app, [("c1", 1, "Hi?", "x"), ("c1", 2, "And?", "x")])
    assert [r["generated_answer"] for r in rows] == ["echo: Hi?", "echo: And?"]
    assert received[0]["session_id"] == received[1]["session_id"] != ""
    assert steps_of(rows[0]) == ["http_call"]


# ---- test_cases.csv ---------------------------------------------------------------------------------------------

def test_the_sample_test_case_file_imports_as_described(served_function):
    app = served_function(lambda question: "x")
    client = TestClient(app)
    sample = (EXAMPLES / "test_cases.csv").read_bytes()
    preview = client.post("/api/test-cases/import/preview", files={"file": ("test_cases.csv", sample, "text/csv")}).json()
    assert preview["counts"]["new"] == 5 and not preview["problems"]
    client.post("/api/test-cases/import", files={"file": ("test_cases.csv", sample, "text/csv")}).raise_for_status()

    cases = {c["question"]: c for c in client.get("/api/test-cases").json()}
    assert len(cases) == 5
    assert cases["Hello!"]["type"] == "non-rag"
    assert (cases["And for an annual plan?"]["chat_id"], cases["And for an annual plan?"]["turn_no"]) == ("refund-1", 2)
    assert cases["When will my order ship?"]["expected_sources"] == "shipping.pdf | tracking.pdf"
    assert cases["How do I track my parcel?"]["expected_sources"] == "tracking.pdf , tracking_v2.pdf"
    assert sorted(g["name"] for g in client.get("/api/groups").json()) == ["Billing", "Shipping", "Small talk"]


# ---- source_checks.py -------------------------------------------------------------------------------------------

def test_expected_sources_with_and_or_are_checked(serve_example):
    app = serve_example("source_checks.py")
    rows = evaluate(app, [
        ("c1", 1, "Can I get a refund?", "30 days"),
        ("c2", 1, "Can I get a refund?", "30 days"),
        ("c3", 1, "Can I get a refund?", "30 days"),
    ], extra={"expected_sources": ["refunds.pdf", "refunds.pdf | shipping.pdf", "refunds_v2.pdf , Refunds.PDF"]})
    assert [r["source_match"] for r in rows] == [True, False, True]
    assert rows[1]["missing_sources"] == ["shipping.pdf"]


# ---- shared_pipeline.py, production_app.py, eval_entry.py -------------------------------------------------------

@pytest.fixture
def example_modules(monkeypatch):
    monkeypatch.syspath_prepend(str(EXAMPLES))
    for name in ("shared_pipeline", "production_app"):
        sys.modules.pop(name, None)
    yield
    for name in ("shared_pipeline", "production_app"):
        sys.modules.pop(name, None)


def test_production_runs_the_same_pipeline_with_steps_doing_nothing(example_modules):
    from ragevalkit.recording.recorder import current_recorder

    import production_app
    reply = TestClient(production_app.app).post("/chat", json={"message": "Can I get a refund?"}).json()
    assert reply == {"reply": "Refunds are allowed within 30 days of purchase."}
    assert current_recorder() is None


def test_the_evaluation_entry_records_the_same_pipeline(example_modules, serve_example):
    row = evaluate(serve_example("eval_entry.py"), [("c1", 1, "Can I get a refund?", "30 days")])[0]
    assert steps_of(row) == ["retrieval", "llm"]
    assert row["sources"] == ["refunds.pdf"] and row["material"] == "Refunds are allowed within 30 days of purchase."


# ---- tool_agent.py ----------------------------------------------------------------------------------------------

def test_an_agent_loop_adds_up_repeated_steps_and_keeps_tool_results_as_material(serve_example):
    row = evaluate(serve_example("tool_agent.py"), [("c1", 1, "Can I return this? Where is order A200?", "x")])[0]
    assert steps_of(row) == ["llm", "lookup_order", "lookup_policy"]
    assert "Order A200 still being packed." in row["material"] and "returned within 30 days" in row["material"]
    assert row["flags"]["tools_used"] == "lookup_order, lookup_policy"
    assert row["generated_answer"] == "Order A200 still being packed. Items can be returned within 30 days."


# ---- langchain_chain.py -----------------------------------------------------------------------------------------

def test_steps_in_parallel_langchain_branches_are_recorded(serve_example):
    pytest.importorskip("langchain_core")
    row = evaluate(serve_example("langchain_chain.py"), [("c1", 1, "Can I get a refund?", "30 days")])[0]
    assert steps_of(row)[0] == "rewrite" and steps_of(row)[-2:] == ["retrieval", "llm"]
    assert {"vector_search", "keyword_search"} <= set(steps_of(row))
    assert row["material"] == "Refunds are allowed within 30 days of purchase." and row["sources"] == ["refunds.pdf"]


# ---- team_setup.py ----------------------------------------------------------------------------------------------

def test_the_team_setup_example_is_a_valid_configuration(serve_example):
    config = serve_example("team_setup.py").state.config
    assert config.eval_users == "alice:pw-for-alice,bob:pw-for-bob" and config.eval_secret == "change-me"
    assert (config.answer_weight, config.material_weight, config.recommendation_tolerance, config.max_response_time) == (0.7, 0.3, 0.2, 8.0)
    assert config.generator_model == "ollama/llama3" and config.logs_dir == Path("evals/logs") and config.store_path == Path("evals/eval_store.json")


# ---- ci_gate.py -------------------------------------------------------------------------------------------------

@pytest.fixture
def running_server(tmp_path):
    """A real server on a free port, with a group of test cases, the way ci_gate.py meets it."""
    config = Config(store_path=tmp_path / "ci_store.json", require_login=False, run_semantic_similarity=False, run_bm25=False)
    app = create_app(config, fn=lambda question: "Refunds are allowed within 30 days.", judge_fn=JUDGE)
    app.state.manager._llm_judge = SimpleNamespace(summarize_run=lambda stats: None)
    store = app.state.store
    group = store.create_group("Billing")
    store.import_into_group(group, pd.DataFrame([("c1", 1, "rag", "Refunds?", "30 days")], columns=COLUMNS))
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(10)
    store.close()


@pytest.mark.parametrize("minimum,exit_code", [("7", 0), ("9", 1)])
def test_the_ci_script_passes_or_fails_the_build_on_answer_quality(running_server, monkeypatch, minimum, exit_code, capsys):
    monkeypatch.setenv("EVAL_URL", running_server)
    monkeypatch.setenv("EVAL_MINIMUM", minimum)
    monkeypatch.setenv("EVAL_VERSION", f"ci-{minimum}")
    script = runpy.run_path(str(EXAMPLES / "ci_gate.py"), run_name="ci_gate")
    script["POLL_SECONDS"] = 0.2
    assert script["run_gate"]() == exit_code
    assert "answer quality 8" in capsys.readouterr().out
