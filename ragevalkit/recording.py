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

WHY thread-local (_ctx = threading.local())
-------------------------------------------
The runner processes each question in the same background thread but
the developer's fn may itself spawn threads (e.g. a multi-agent system).
Thread-local storage means each thread has its own active flag and buffer,
so parallel calls inside fn() don't cross-contaminate each other's steps.

WHY _deactivate() is in a finally block in runner.py
-----------------------------------------------------
If fn() raises an exception the finally block still clears the flag, so
the next question's _activate() starts with a clean slate rather than
accumulating stale steps from a failed call.

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
# Repr helper
# -----------------------------------------------------------------------

def _safe_repr(v, max_len: int = 400) -> str:
    """Stringify any value for storage — truncated to avoid bloating the receipt."""
    if isinstance(v, str):
        return v[:max_len]
    try:
        s = json.dumps(v, default=str, ensure_ascii=False)
    except Exception:
        s = str(v)
    return s[:max_len]


# -----------------------------------------------------------------------
# Thread-local context
# -----------------------------------------------------------------------

# One thread-local object shared by all _StepContext instances.
# Each thread gets its own .active, .steps, .flags, and .detail attributes.
_ctx = threading.local()


def _get_ctx():
    if not hasattr(_ctx, "active"):
        _ctx.active = False
        _ctx.steps = []
        _ctx.flags = {}
        _ctx.detail = "all"
    return _ctx


def _activate(detail: str = "all") -> None:
    """Called by RunManager before invoking the developer's fn()."""
    c = _get_ctx()
    c.active = True
    c.steps = []          # fresh step buffer for this question
    c.flags = {}          # fresh flag buffer for this question
    c.detail = detail     # "all" | "selected" | "off"


def _deactivate() -> None:
    """Called by RunManager in a finally block — always runs, even if fn() raises."""
    _get_ctx().active = False


def _collect() -> dict:
    """Drain and return recorded steps and flags. Called once after fn() returns."""
    c = _get_ctx()
    result = {"steps": list(c.steps), "flags": dict(c.flags)}
    c.steps = []
    c.flags = {}
    return result


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

    No-op when called outside an active eval run. Secret key names (containing
    "password", "token", "key", etc.) are silently dropped.
    """
    c = _get_ctx()
    if c.active and not _is_secret(key):
        c.flags[key] = _safe_repr(value)


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

    def __init__(self, name: str):
        self.name = name
        self._material: str = ""
        self._material_explicit: bool = False
        self._sources: list = []
        self._sources_explicit: bool = False
        self.inputs: dict = {}    # only populated when used as a decorator
        self.output: str = ""     # only populated when used as a decorator
        self._start: float = 0.0

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

    def _emit(self, elapsed: float) -> None:
        c = _get_ctx()
        if not c.active:
            return
        detail = c.detail

        if detail == "off":
            # Only record name and timing; skip all content.
            c.steps.append({"name": self.name, "elapsed": elapsed})
            return

        if detail == "selected":
            # Only emit if developer explicitly provided material or sources.
            if not self._material_explicit and not self._sources_explicit:
                return

        c.steps.append({
            "name":     self.name,
            "elapsed":  elapsed,
            "material": self._material,
            "sources":  self.sources,
            "inputs":   self.inputs  if detail == "all" else {},
            "output":   self.output  if detail == "all" else "",
        })

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
                ctx = _StepContext(self.name)
                ctx.inputs = _capture_inputs(args, kwargs)
                ctx._start = _time.perf_counter()
                result = None
                try:
                    result = await fn(*args, **kwargs)
                    return result
                finally:
                    ctx.output = _safe_repr(result)
                    # Auto-set material from return value (not explicit — won't trigger "selected" mode).
                    if not ctx._material_explicit:
                        ctx._material = ctx.output
                    ctx._emit(round(_time.perf_counter() - ctx._start, 3))
            return async_wrapper

        @wraps(fn)
        def wrapper(*args, **kwargs):
            ctx = _StepContext(self.name)
            ctx.inputs = _capture_inputs(args, kwargs)
            ctx._start = _time.perf_counter()
            result = None
            try:
                result = fn(*args, **kwargs)
                return result
            finally:
                ctx.output = _safe_repr(result)
                if not ctx._material_explicit:
                    ctx._material = ctx.output
                ctx._emit(round(_time.perf_counter() - ctx._start, 3))
        return wrapper


# -----------------------------------------------------------------------
# Public step() factory
# -----------------------------------------------------------------------

def step(name: str) -> _StepContext:
    """
    Record a named pipeline step's execution time (and optionally its retrieved material).

    As a decorator::

        @ragevalkit.step("retriever")
        def retrieve(query): ...

    As a context manager::

        with ragevalkit.step("retriever") as s:
            docs = vector_db.search(query)
            s.material = "\\n".join(d.text for d in docs)
            s.sources = [d.id for d in docs]

    No-op when called outside an active eval run (zero overhead in production).
    Secret-named parameters (password, token, key, etc.) are auto-redacted.
    """
    return _StepContext(name)
