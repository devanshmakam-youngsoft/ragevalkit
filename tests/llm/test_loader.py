"""litellm is loaded once, completely, before threads can race over it."""
import sys
import threading
import types

from ragevalkit.config import Config
from ragevalkit.generation.model_client import GenerationModelClient
from ragevalkit.llm import loader


def fake_litellm(monkeypatch):
    module = types.ModuleType("litellm")
    module.completion = lambda **kw: types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="{}"))])
    monkeypatch.setitem(sys.modules, "litellm", module)
    return module


def test_the_parts_litellm_loads_lazily_are_loaded_up_front(monkeypatch):
    fake_litellm(monkeypatch)
    loaded = []
    for name in loader._LAZY_PARTS:
        part = types.ModuleType(name)
        monkeypatch.setitem(sys.modules, name, part)
    real = loader.importlib.import_module
    monkeypatch.setattr(loader.importlib, "import_module", lambda name: loaded.append(name) or real(name))
    loader.load_litellm()
    assert loaded == list(loader._LAZY_PARTS)


def test_a_litellm_without_those_parts_still_loads(monkeypatch):
    module = fake_litellm(monkeypatch)
    for name in loader._LAZY_PARTS:
        monkeypatch.delitem(sys.modules, name, raising=False)
    assert loader.load_litellm() is module


def test_threads_never_load_litellm_at_the_same_time(monkeypatch):
    fake_litellm(monkeypatch)
    inside, worst = [0], [0]
    guard = threading.Lock()
    real = loader.importlib.import_module

    def slow_import(name):
        with guard:
            inside[0] += 1
            worst[0] = max(worst[0], inside[0])
        threading.Event().wait(0.02)
        with guard:
            inside[0] -= 1
        return real(name)

    for name in loader._LAZY_PARTS:
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setattr(loader.importlib, "import_module", slow_import)
    model = GenerationModelClient(Config(store_path="x", judge_model="m"))
    threads = [threading.Thread(target=model, args=([{"role": "user", "content": "hi"}],)) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert worst[0] == 1


def test_litellms_help_banner_is_switched_off(monkeypatch):
    module = fake_litellm(monkeypatch)
    module.suppress_debug_info = False
    assert loader.load_litellm().suppress_debug_info is True
