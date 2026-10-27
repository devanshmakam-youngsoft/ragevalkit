"""
Step recording — the zero-overhead observability layer for ragevalkit.

HOW IT WORKS
------------
`ragevalkit.step("name")` returns a _StepContext that does nothing at all
unless the current thread is inside an active eval run.

When the RunManager calls the developer's function it:
  1. calls _activate(detail)  → sets this thread's "active" flag + clears the step/flag buffers
  2. calls fn(question)       → developer code runs; any @step / with step: fires _emit()
  3. calls _deactivate()      → clears the active flag  (in a finally block — always runs)
  4. calls _collect()         → drains the buffers and returns {"steps": [...], "flags": {...}}

WHY a recorder per question, not per thread
------------------------------------------
The runner handles ONE question at a time (and one run at a time), so everything recorded while ``fn()`` is
running belongs to that question, whichever thread records it. Pipelines often search several indexes in a
thread pool, or hand work to an executor; a step started there still lands in the current question's recorder.
Each step takes hold of its recorder when it STARTS, so a slow leftover thread from question 1 can never add
its step to question 2: once a question is collected its recorder is closed and late steps are ignored.

WHY _deactivate() is in a finally block in runner.py
-----------------------------------------------------
If fn() raises an exception the finally block still closes the recorder, so the next question's
_activate() starts with a clean slate rather than accumulating stale steps from a failed call.

WHAT BECOMES "MATERIAL" (the retrieved text the judge scores)
-------------------------------------------------------------
Only a step that DECLARES its material: ``s.material = ...`` inside ``with step(...)``, or
``@step("retrieval", material=True)`` which takes the decorated function's return value. If no step declares
anything, the output of decorated steps is used (how earlier versions behaved), and a warning says how to be
explicit. Material is cut at ``max_material_chars`` (default 20,000) with a visible marker, and the displayed
inputs, outputs and notes at ``max_step_value_chars`` (default 1,000).

SECRET BLANKING
---------------
Any step input parameter whose name contains a secret-related keyword
(password, token, key, secret, auth, bearer, credential) is replaced with
"[REDACTED]" before storing.

RECORDING DETAIL LEVELS
------------------------
"all"      — capture inputs, outputs, material, sources, timing (default)
"selected" — only emit steps where developer explicitly set .material or .sources
"off"      — only record step name + elapsed time (no content)
"""
import inspect
import json
import threading
import time as _time
from functools import wraps

# -----------------------------------------------------------------------
# Secret detection
# -----------------------------------------------------------------------

_SECRET_FRAGMENTS = frozenset({
    "password", "passwd", "pwd", "secret", "api_key", "apikey",
    "token", "auth", "bearer", "credential", "credentials", "authorization",
    "access_key", "private_key",
})


def _is_secret(name: str) -> bool:
    n = name.lower().replace("-", "_")
    return any(frag in n for frag in _SECRET_FRAGMENTS)


# -----------------------------------------------------------------------
# Limits and the repr helper
# -----------------------------------------------------------------------

_limits = {"value": 1000, "material": 20000}


def configure(max_step_value_chars: int | None = None, max_material_chars: int | None = None) -> None:
    """Set how much is kept: shown step inputs/outputs/notes, and the material the judge reads."""
    if max_step_value_chars:
        _limits["value"] = int(max_step_value_chars)
    if max_material_chars:
        _limits["material"] = int(max_material_chars)


def _clip(text: str, limit: int) -> str:
    """The text, or its first ``limit`` characters followed by a marker saying how much was left out."""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\u2026 (+{len(text) - limit} more characters)"


def clip_material(text: str) -> str:
    return _clip(text, _limits["material"])


def _is_number_list(v) -> bool:
    return (isinstance(v, (list, tuple)) and len(v) >= 32
            and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v))


def _text_of(v) -> str:
    if isinstance(v, str):
        return v
    try:
        return json.dumps(v, default=str, ensure_ascii=False)
    except Exception:
        return str(v)


def _safe_repr(v, max_len: int | None = None) -> str:
    """Stringify any value for storage: cut to the display limit (with a marker), and a long list of numbers
    (an embedding vector, say) is summarised instead of printed."""
    if _is_number_list(v):
        return f"[{len(v)} numbers]"
    return _clip(_text_of(v), max_len or _limits["value"])


# -----------------------------------------------------------------------
# The recorder: everything recorded during one question
# -----------------------------------------------------------------------

class _Recorder:
    def __init__(self, detail: str):
        self.detail = detail          # "all" | "selected" | "off"
        self.steps: list[dict] = []
        self.flags: dict = {}
        self.open = True              # closed when the question is over: late steps are ignored
        self._seq = 0
        self.lock = threading.Lock()

    def next_seq(self) -> int:
        with self.lock:
            self._seq += 1
            return self._seq


_lock = threading.Lock()
_current: _Recorder | None = None     # the question being run right now (None outside an eval run)
_finished: _Recorder | None = None    # the question that just ended, until _collect() reads it


def _activate(detail: str = "all") -> None:
    """Called by RunManager before invoking the developer's fn(): a fresh recorder for this question."""
    global _current, _finished
    with _lock:
        _current, _finished = _Recorder(detail), None


def _deactivate() -> None:
    """Called by RunManager in a finally block (always runs, even if fn() raises): close the recorder."""
    global _current, _finished
    with _lock:
        if _current is not None:
            _current.open = False
            _finished, _current = _current, None


def _collect() -> dict:
    """The steps (in the order they started) and notes of the question that just ended."""
    global _finished
    with _lock:
        rec = _finished or _current
        _finished = None
    if rec is None:
        return {"steps": [], "flags": {}}
    with rec.lock:
        return {"steps": [s for _, s in sorted(rec.steps, key=lambda item: item[0])], "flags": dict(rec.flags)}


# -----------------------------------------------------------------------
# Public note() API
# -----------------------------------------------------------------------

def note(key: str, value) -> None:
    """Record a free-form flag/note attached to the current question.

    Use this to annotate what the question is testing, expected intent,
    difficulty, or any other metadata you want visible in the receipt.

    As a regular call::

        ragevalkit.note("intent", "billing")
        ragevalkit.note("difficulty", "hard")
        ragevalkit.note("expected_tool", "invoice_lookup")

    No-op when called outside an active eval run. Works from any thread. Secret key names (containing
    "password", "token", "key", etc.) are silently dropped.
    """
    rec = _current
    if rec is not None and rec.open and not _is_secret(key):
        with rec.lock:
            rec.flags[key] = _safe_repr(value)


# -----------------------------------------------------------------------
# _StepContext
# -----------------------------------------------------------------------

class _StepContext:
    """
    The object returned by step("name").

    Dual-mode:
      • context manager  → developer controls timing manually with `with`
      • decorator        → wraps a function; timing + I/O captured automatically

    Public attributes (readable/writable in context-manager mode):
      .material  — the retrieved text this step returned (sent to the judge)
      .sources   — list of source identifiers (doc IDs, URLs, etc.)

    Setting .material or .sources explicitly marks the step as "selected",
    so it is always recorded even in record_detail="selected" mode.
    """

    def __init__(self, name: str, material: bool = False):
        self.name = name
        self._returns_material = material     # decorator: the return value is the retrieved text
        self._material: str = ""
        self._material_explicit: bool = False
        self._sources: list = []
        self._sources_explicit: bool = False
        self.inputs: dict = {}    # only populated when used as a decorator
        self.output: str = ""     # only populated when used as a decorator
        self._start: float = 0.0
        # take hold of the question's recorder now, so the step still belongs to it if it ends in another thread
        self._rec = _current
        self._seq = self._rec.next_seq() if self._rec is not None else 0

    @property
    def material(self) -> str:
        return self._material

    @material.setter
    def material(self, value: str) -> None:
        self._material = value
        self._material_explicit = True

    @property
    def sources(self) -> list:
        return self._sources

    @sources.setter
    def sources(self, value: list) -> None:
        self._sources = value
        self._sources_explicit = True

    def _finish_decorated(self, result) -> None:
        """What a decorated function returned: shown (cut), and offered as material (declared or not)."""
        self.output = _safe_repr(result)
        if not self._material_explicit:
            self._material = _text_of(result) if result is not None else ""
            self._material_explicit = self._returns_material      # declared only with material=True

    def _emit(self, elapsed: float) -> None:
        rec = self._rec
        if rec is None or not rec.open:
            return
        detail = rec.detail

        if detail == "off":
            # Only record name and timing; skip all content.
            entry = {"name": self.name, "elapsed": elapsed}
        else:
            if detail == "selected" and not self._material_explicit and not self._sources_explicit:
                return        # only steps where the developer provided material or sources
            entry = {
                "name":     self.name,
                "elapsed":  elapsed,
                "material": self._material or "",         # cut once, where the steps are joined (runner._material_of)
                "material_declared": self._material_explicit,
                "sources":  self.sources,
                "inputs":   self.inputs  if detail == "all" else {},
                "output":   self.output  if detail == "all" else "",
            }
        with rec.lock:
            rec.steps.append((self._seq, entry))

    # --- context manager ---
    def __enter__(self):
        self._start = _time.perf_counter()
        return self  # `as s` → developer can set s.material, s.sources

    def __exit__(self, *_):
        # Runs even if the body raised — timing is always recorded.
        self._emit(round(_time.perf_counter() - self._start, 3))

    # --- decorator (sync + async) ---
    def __call__(self, fn):
        # Capture the signature once at decoration time (not per call).
        sig = inspect.signature(fn)

        def _capture_inputs(args, kwargs) -> dict:
            """Bind call args to param names; redact secret-named params."""
            try:
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                return {
                    k: "[REDACTED]" if _is_secret(k) else _safe_repr(v)
                    for k, v in bound.arguments.items()
                }
            except Exception:
                return {}

        if inspect.iscoroutinefunction(fn):
            @wraps(fn)
            async def async_wrapper(*args, **kwargs):
                ctx = _StepContext(self.name, self._returns_material)
                ctx.inputs = _capture_inputs(args, kwargs)
                ctx._start = _time.perf_counter()
                result = None
                try:
                    result = await fn(*args, **kwargs)
                    return result
                finally:
                    ctx._finish_decorated(result)
                    ctx._emit(round(_time.perf_counter() - ctx._start, 3))
            return async_wrapper

        @wraps(fn)
        def wrapper(*args, **kwargs):
            ctx = _StepContext(self.name, self._returns_material)
            ctx.inputs = _capture_inputs(args, kwargs)
            ctx._start = _time.perf_counter()
            result = None
            try:
                result = fn(*args, **kwargs)
                return result
            finally:
                ctx._finish_decorated(result)
                ctx._emit(round(_time.perf_counter() - ctx._start, 3))
        return wrapper


# -----------------------------------------------------------------------
# Public step() factory
# -----------------------------------------------------------------------

def step(name: str, *, material: bool = False) -> _StepContext:
    """
    Record a named pipeline step's execution time (and optionally its retrieved material).

    As a decorator::

        @ragevalkit.step("retrieval", material=True)    # the return value is the retrieved text
        def retrieve(query): ...

        @ragevalkit.step("rewrite")                     # timing and inputs/outputs only
        def rewrite(query): ...

    As a context manager::

        with ragevalkit.step("retrieval") as s:
            docs = vector_db.search(query)
            s.material = "\\n".join(d.text for d in docs)
            s.sources = [d.id for d in docs]

    Works from any thread (a step run in a thread pool still belongs to the question being evaluated).
    No-op when called outside an active eval run (zero overhead in production).
    Secret-named parameters (password, token, key, etc.) are auto-redacted.
    """
    return _StepContext(name, material)
