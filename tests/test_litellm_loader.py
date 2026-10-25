"""litellm is loaded once, completely, before threads can race over it (see ragevalkit/litellm_loader.py)."""
import sys
import threading
import types

from ragevalkit import litellm_loader
from ragevalkit.config import Config
from ragevalkit.generator.llm import LiteLLM


def fake_litellm(monkeypatch):
    module = types.ModuleType("litellm")
    module.completion = lambda **kw: types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="{}"))])
    monkeypatch.setitem(sys.modules, "litellm", module)
    return module


def test_the_parts_litellm_loads_lazily_are_loaded_up_front(monkeypatch):
    fake_litellm(monkeypatch)
    loaded = []
    for name in litellm_loader._LAZY_PARTS:
        part = types.ModuleType(name)
        monkeypatch.setitem(sys.modules, name, part)
    real = litellm_loader.importlib.import_module
    monkeypatch.setattr(litellm_loader.importlib, "import_module", lambda name: loaded.append(name) or real(name))
    litellm_loader.load()
    assert loaded == list(litellm_loader._LAZY_PARTS)


def test_a_litellm_without_those_parts_still_loads(monkeypatch):
    module = fake_litellm(monkeypatch)
    for name in litellm_loader._LAZY_PARTS:
        monkeypatch.delitem(sys.modules, name, raising=False)
    assert litellm_loader.load() is module


def test_threads_never_load_litellm_at_the_same_time(monkeypatch):
    fake_litellm(monkeypatch)
    inside, worst = [0], [0]
    guard = threading.Lock()
    real = litellm_loader.importlib.import_module

    def slow_import(name):
        with guard:
            inside[0] += 1
            worst[0] = max(worst[0], inside[0])
        threading.Event().wait(0.02)
        with guard:
            inside[0] -= 1
        return real(name)

    for name in litellm_loader._LAZY_PARTS:
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setattr(litellm_loader.importlib, "import_module", slow_import)
    model = LiteLLM(Config(store_path="x", judge_model="m"))
    threads = [threading.Thread(target=model, args=([{"role": "user", "content": "hi"}],)) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert worst[0] == 1


def test_the_writer_and_the_judge_both_go_through_the_loader(monkeypatch):
    from ragevalkit.judge import Judge

    module = fake_litellm(monkeypatch)
    calls = []
    monkeypatch.setattr(litellm_loader, "load", lambda: calls.append(1) or module)
    LiteLLM(Config(store_path="x", judge_model="m"))([{"role": "user", "content": "hi"}])
    Judge(Config(store_path="x", judge_model="m"))._call([{"role": "user", "content": "hi"}])
    assert len(calls) == 2
