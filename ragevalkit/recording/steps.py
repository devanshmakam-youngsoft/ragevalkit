"""``step()``: time a stage of your pipeline and say what it retrieved."""
import inspect
import time as _time
from functools import wraps

from ragevalkit.recording.limits import display_text, text_of
from ragevalkit.recording.recorder import current_recorder
from ragevalkit.recording.redaction import is_secret_name


class StepContext:
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
        self._rec = current_recorder()
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
        self.output = display_text(result)
        if not self._material_explicit:
            self._material = text_of(result) if result is not None else ""
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
                    k: "[REDACTED]" if is_secret_name(k) else display_text(v)
                    for k, v in bound.arguments.items()
                }
            except Exception:
                return {}

        if inspect.iscoroutinefunction(fn):
            @wraps(fn)
            async def async_wrapper(*args, **kwargs):
                ctx = StepContext(self.name, self._returns_material)
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
            ctx = StepContext(self.name, self._returns_material)
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


def step(name: str, *, material: bool = False) -> StepContext:
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
    return StepContext(name, material)
