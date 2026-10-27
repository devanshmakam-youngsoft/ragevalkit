"""Step recording: steps from any thread, material that is declared, and the limits on what is kept."""
import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from ragevalkit import recording
from ragevalkit.config import Config
from ragevalkit.runner import _material_of
from ragevalkit.server import create_app


def run_question(body, detail="all"):
    """What the runner does around one call of the developer's function."""
    recording.begin_question(detail)
    try:
        body()
    finally:
        recording.end_question()
    return recording.collect_question()


@pytest.fixture(autouse=True)
def default_limits(monkeypatch):
    monkeypatch.setitem(recording.LIMITS, "value", 1000)
    monkeypatch.setitem(recording.LIMITS, "material", 20000)


# ---- steps and notes from any thread --------------------------------------------------------------------

def test_steps_started_in_a_thread_pool_are_recorded_with_their_material_and_sources():
    def search(name, delay):
        with recording.step(name) as s:
            time.sleep(delay)
            s.material = f"text from {name}"
            s.sources = [f"{name}.pdf"]

    def body():
        with ThreadPoolExecutor(2) as pool:
            list(pool.map(lambda args: search(*args), [("index_a", 0.05), ("index_b", 0.01)]))

    got = run_question(body)
    steps = {s["name"]: s for s in got["steps"]}
    assert set(steps) == {"index_a", "index_b"}
    assert steps["index_a"]["elapsed"] >= 0.05 and steps["index_b"]["sources"] == ["index_b.pdf"]
    assert _material_of(got["steps"]).count("text from") == 2


def test_notes_from_a_thread_reach_the_question():
    def body():
        with ThreadPoolExecutor(1) as pool:
            pool.submit(lambda: recording.note("intent", "billing")).result()

    assert run_question(body)["flags"] == {"intent": "billing"}


def test_steps_are_listed_in_the_order_they_started_not_the_order_they_finished():
    def body():
        first, second = recording.step("first"), recording.step("second")      # started in this order...
        with second:
            pass
        with first:                                                              # ...finished in the other
            pass

    assert [s["name"] for s in run_question(body)["steps"]] == ["first", "second"]


def test_a_step_that_finishes_after_its_question_is_over_does_not_land_in_the_next_one():
    recording.begin_question("all")
    late = recording.step("late")
    late.__enter__()
    recording.end_question()
    assert recording.collect_question()["steps"] == []

    recording.begin_question("all")
    late.__exit__(None, None, None)                  # the slow thread from question 1 ends during question 2
    recording.end_question()
    assert recording.collect_question()["steps"] == []


def test_async_steps_run_together_are_all_recorded():
    async def work(name):
        with recording.step(name):
            await asyncio.sleep(0.01)

    async def main():
        await asyncio.gather(work("a"), work("b"))

    assert {s["name"] for s in run_question(lambda: asyncio.run(main()))["steps"]} == {"a", "b"}


def test_nothing_is_recorded_outside_an_evaluation_run():
    with recording.step("outside") as s:
        s.material = "x"
    recording.note("k", "v")
    assert recording.collect_question() == {"steps": [], "flags": {}}


def test_detail_modes_keep_what_they_promise():
    def body():
        with recording.step("quiet"):
            pass
        with recording.step("loud") as s:
            s.material = "retrieved"

    assert {s["name"] for s in run_question(body, "selected")["steps"]} == {"loud"}
    off = run_question(body, "off")["steps"]
    assert {s["name"] for s in off} == {"quiet", "loud"} and all(set(s) == {"name", "elapsed"} for s in off)


# ---- what counts as the retrieved text ------------------------------------------------------------------

@recording.step("rewrite")
def rewrite(q):
    return "rewritten " + q


@recording.step("retrieval", material=True)
def retrieve(q):
    return "DOCUMENT TEXT " * 100              # 1,400 characters: far more than the old 400-character cut


@recording.step("llm")
def generate(q):
    return "THE ANSWER ITSELF"


def test_only_the_step_that_declares_material_supplies_it_in_full():
    def body():
        rewrite("q"), retrieve("q"), generate("q")

    steps = run_question(body)["steps"]
    material = _material_of(steps)
    assert material == "DOCUMENT TEXT " * 100            # whole, not cut at 400
    assert "THE ANSWER" not in material and "rewritten" not in material


def test_a_context_manager_that_sets_material_also_counts_as_declared():
    def body():
        generate("q")
        with recording.step("search") as s:
            s.material = "from the search"

    assert _material_of(run_question(body)["steps"]) == "from the search"


def test_when_nothing_is_declared_decorated_outputs_are_still_used_and_the_log_explains(caplog, monkeypatch):
    import ragevalkit.runner as runner
    monkeypatch.setattr(runner, "_warned_undeclared_material", False)

    @recording.step("search")
    def search(q):
        return "found text"

    steps = run_question(lambda: (search("q"), generate("q")))["steps"]
    with caplog.at_level(logging.WARNING, logger="ragevalkit.runner"):
        assert _material_of(steps) == "found text\n\nTHE ANSWER ITSELF"        # how earlier versions behaved
        _material_of(steps)
    warnings = [r.getMessage() for r in caplog.records if "No step declared its material" in r.getMessage()]
    assert len(warnings) == 1 and "material=True" in warnings[0] and "search, llm" in warnings[0]


def test_a_single_undeclared_step_is_taken_as_the_retriever_without_a_warning(caplog, monkeypatch):
    import ragevalkit.runner as runner
    monkeypatch.setattr(runner, "_warned_undeclared_material", False)

    @recording.step("search")
    def search(q):
        return "found text"

    with caplog.at_level(logging.WARNING, logger="ragevalkit.runner"):
        assert _material_of(run_question(lambda: search("q"))["steps"]) == "found text"
    assert not caplog.records


# ---- the limits ----------------------------------------------------------------------------------------

def test_shown_values_are_cut_with_a_marker_saying_how_much_is_missing():
    @recording.step("step")
    def long_output(text):
        return text

    steps = run_question(lambda: long_output("x" * 1500))["steps"]
    assert steps[0]["output"] == "x" * 1000 + "… (+500 more characters)"
    assert steps[0]["inputs"]["text"].endswith("(+500 more characters)")


def test_material_is_cut_at_its_own_larger_limit(monkeypatch):
    monkeypatch.setitem(recording.LIMITS, "material", 50)

    def body():
        with recording.step("search") as s:
            s.material = "m" * 80

    material = _material_of(run_question(body)["steps"])
    assert material == "m" * 50 + "… (+30 more characters)"


def test_the_limits_can_be_set():
    recording.configure(max_step_value_chars=7, max_material_chars=9)
    try:
        assert recording.LIMITS == {"value": 7, "material": 9}
    finally:
        recording.configure(max_step_value_chars=1000, max_material_chars=20000)


def test_a_vector_is_summarised_not_stored():
    @recording.step("embed")
    def embed(q):
        return [0.1] * 1536

    assert run_question(lambda: embed("q"))["steps"][0]["output"] == "[1536 numbers]"
    assert recording.display_text([1, 2, 3]) == "[1, 2, 3]"           # a short list is shown as it is


# ---- through the runner --------------------------------------------------------------------------------

def make_manager(tmp_path, fn):
    app = create_app(Config(store_path=tmp_path / "s.json", require_login=False, eval_secret="s"), fn=fn, generation_llm=lambda m: "{}")
    return app.state.manager


def test_a_step_that_ran_several_times_has_its_time_added_up(tmp_path):
    def fn(question):
        with ThreadPoolExecutor(2) as pool:                    # the same search, on two indexes at once
            list(pool.map(lambda _: _timed_search(), range(2)))
        with recording.step("llm"):
            time.sleep(0.01)
        return "answer"

    def _timed_search():
        with recording.step("search") as s:
            time.sleep(0.05)
            s.material = "chunk"

    answer, elapsed, timings, material, sources, _, _, _ = make_manager(tmp_path, fn)._call_fn("q", [], "s1")
    assert answer == "answer" and list(timings) == ["search", "llm"]
    assert timings["search"] >= 0.1 and timings["llm"] >= 0.01        # both searches counted, not just the last
    assert material == "chunk\n\nchunk"


def test_the_runner_applies_the_configured_limits(tmp_path):
    config = Config(store_path=tmp_path / "s.json", require_login=False, eval_secret="s", step_value_chars=30, material_chars=40)
    app = create_app(config, fn=lambda q: "a", generation_llm=lambda m: "{}")
    assert recording.LIMITS == {"value": 30, "material": 40}
    recording.configure(max_step_value_chars=1000, max_material_chars=20000)
    del app
