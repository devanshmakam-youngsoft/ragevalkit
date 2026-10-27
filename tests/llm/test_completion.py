"""The one model call: JSON mode falls back when a provider rejects it, and everyone goes through it."""
import sys
import types

from ragevalkit.config import Config
from ragevalkit.generator.llm import LiteLLM
from ragevalkit.judge import Judge
from ragevalkit.llm import completion


def fake_litellm(monkeypatch):
    module = types.ModuleType("litellm")
    module.completion = lambda **kw: types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="{}"))])
    monkeypatch.setitem(sys.modules, "litellm", module)
    return module


def test_the_writer_and_the_judge_both_go_through_the_one_model_call(monkeypatch):
    module = fake_litellm(monkeypatch)
    calls = []
    monkeypatch.setattr(completion, "load_litellm", lambda: calls.append(1) or module)
    LiteLLM(Config(store_path="x", judge_model="m"))([{"role": "user", "content": "hi"}])
    Judge(Config(store_path="x", judge_model="m"))._call([{"role": "user", "content": "hi"}])
    assert len(calls) == 2


def test_a_json_mode_rejection_is_logged_once_in_our_words_and_the_retry_still_answers(monkeypatch, caplog):
    module = fake_litellm(monkeypatch)
    seen = []

    def completion_stub(**kw):
        seen.append("response_format" in kw)
        if "response_format" in kw:
            raise RuntimeError("GroqException - json_validate_failed: Failed to validate JSON\nmore detail")
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content='{"ok": 1}'))])

    module.completion = completion_stub
    with caplog.at_level("INFO", logger="ragevalkit.llm.completion"):
        reply = LiteLLM(Config(store_path="x", judge_model="groq/m"))([{"role": "user", "content": "hi"}])
    assert reply == '{"ok": 1}' and seen == [True, False]
    assert [r.getMessage() for r in caplog.records if "rejected JSON mode" in r.getMessage()] == [
        "groq/m rejected JSON mode (GroqException - json_validate_failed: Failed to validate JSON); asking again without it"]


def test_the_judge_also_falls_back_from_json_mode_instead_of_failing(monkeypatch):
    module = fake_litellm(monkeypatch)
    seen = []

    def completion_stub(**kw):
        seen.append("response_format" in kw)
        if "response_format" in kw:
            raise RuntimeError("json_validate_failed: Failed to validate JSON")
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="{}"))])

    module.completion = completion_stub
    assert Judge(Config(store_path="x", judge_model="groq/m"))._call([{"role": "user", "content": "hi"}], json_mode=True) == "{}"
    assert seen == [True, False]
    seen.clear()
    Judge(Config(store_path="x", judge_model="groq/m"))._call([{"role": "user", "content": "hi"}])      # no JSON mode asked: none used
    assert seen == [False]
