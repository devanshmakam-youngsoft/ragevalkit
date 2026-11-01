"""Calling your pipeline function: which arguments it takes, how its answer is read, how history is passed."""
import asyncio
import inspect
from typing import Callable


def detect_call_style(fn: Callable, session_aliases: list[str], history_aliases: list[str]) -> str:
    """Returns 'session_id' | 'history' | 'question' based on fn's parameter names.

    Priority: session_id > history > question.
    A function that accepts a session_id is assumed to be stateful (manages its own
    conversation history); the runner still builds history but passes it only to
    functions that explicitly declare a history parameter.
    """
    s_aliases, h_aliases = set(session_aliases), set(history_aliases)
    params = set(inspect.signature(fn).parameters)
    if params & s_aliases:
        return "session_id"
    if params & h_aliases:
        return "history"
    return "question"


def parameter_name_for(fn: Callable, aliases: set[str]) -> str:
    """Return the actual parameter name from fn that matches one of the aliases."""
    matched = set(inspect.signature(fn).parameters) & aliases
    return next(iter(matched), list(aliases)[0])


def answer_text_of(result, answer_keys: list[str]) -> str:
    """
    Turn any RAG function return value into a plain string.
    Handles str, dict (tries answer_keys in order), pydantic model, or any object.
    """
    keys = answer_keys
    if isinstance(result, str):
        return result
    if hasattr(result, "model_dump"):
        result = result.model_dump()
    elif hasattr(result, "dict") and callable(result.dict):
        try:
            result = result.dict()
        except Exception:
            pass
    if isinstance(result, dict):
        for key in keys:
            if key in result:
                return str(result[key]) if not isinstance(result[key], str) else result[key]
        import json
        try:
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception:
            return str(result)
    for key in keys:
        val = getattr(result, key, None)
        if val is not None:
            return str(val)
    return str(result)


def call_sync(fn: Callable, *args, **kwargs):
    """Call fn whether it is sync or async; always returns synchronously."""
    if inspect.iscoroutinefunction(fn):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    return ex.submit(asyncio.run, fn(*args, **kwargs)).result()
            return loop.run_until_complete(fn(*args, **kwargs))
        except RuntimeError:
            return asyncio.run(fn(*args, **kwargs))
    return fn(*args, **kwargs)


def format_history(turns: list[dict], fmt: str) -> list[dict]:
    """
    Convert internal history to the format the developer's function expects.

    fmt="dict"   → [{"question": "...", "answer": "..."}]   (default)
    fmt="openai" → [{"role": "user", "content": "..."},
                    {"role": "assistant", "content": "..."}]
    """
    if fmt == "openai":
        msgs = []
        for t in turns:
            msgs.append({"role": "user",      "content": t.get("question", "")})
            msgs.append({"role": "assistant", "content": t.get("answer",   "")})
        return msgs
    return list(turns)  # default "dict" format
