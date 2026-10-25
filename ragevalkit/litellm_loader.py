"""Loading litellm without tripping over itself.

litellm takes seconds to import, and it loads parts of itself lazily: the first log record after it is loaded
makes its logging filter import more modules. When two threads do this at the same moment (a worker calling the
model while the web server logs a request) Python reports "deadlock detected by _ModuleLock" or hands out a
half-loaded module with "no attribute 'completion'". ``load`` finishes all of it, once, under a lock;
``serve`` calls it at start-up, before any other thread exists.
"""
from __future__ import annotations

import importlib
import logging
import threading

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_LAZY_PARTS = ("litellm.rust_bridge.diagnostics", "litellm.rust_bridge.catalog")   # imported on first log record

# errors that mean "this provider's JSON mode does not like this", after which asking without it is worth a try
JSON_MODE_ERRORS = ("response_format", "json_validate_failed", "failed to validate json", "json mode", "json_object")


def load():
    """The litellm module, fully loaded."""
    with _lock:
        import litellm

        for name in _LAZY_PARTS:
            try:
                importlib.import_module(name)
            except Exception:       # not every litellm version has these parts
                pass
        litellm.suppress_debug_info = True     # no "Give Feedback / Get Help" banner on every handled error; failures are logged by us
    return litellm


def complete(messages: list[dict], *, model: str, api_key: str | None = None, temperature: float | None = None,
             json_mode: bool = False) -> str:
    """One model call, returning the reply text. With ``json_mode`` the provider is asked for a JSON object; one that
    has no JSON mode, or whose JSON mode rejects the output (Groq: "Failed to validate JSON"), is asked again without
    it. The prompts already require JSON and replies are read leniently, so the retry costs nothing in quality."""
    litellm = load()
    kwargs: dict = dict(model=model, messages=messages)
    if temperature is not None:
        kwargs["temperature"] = temperature
    if api_key:
        kwargs["api_key"] = api_key
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        resp = litellm.completion(**kwargs)
    except Exception as e:
        if not (json_mode and any(key in str(e).lower() for key in JSON_MODE_ERRORS)):
            raise
        logger.info("%s rejected JSON mode (%s); asking again without it", model, str(e).splitlines()[0][:160])
        kwargs.pop("response_format")
        resp = litellm.completion(**kwargs)
    return resp.choices[0].message.content
