"""The recorder: everything recorded during one question, whichever thread records it."""
import threading


class Recorder:
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


_current: Recorder | None = None     # the question being run right now (None outside an eval run)


_finished: Recorder | None = None    # the question that just ended, until collect_question() reads it


def begin_question(detail: str = "all") -> None:
    """Called by RunManager before invoking the developer's fn(): a fresh recorder for this question."""
    global _current, _finished
    with _lock:
        _current, _finished = Recorder(detail), None


def end_question() -> None:
    """Called by RunManager in a finally block (always runs, even if fn() raises): close the recorder."""
    global _current, _finished
    with _lock:
        if _current is not None:
            _current.open = False
            _finished, _current = _current, None


def collect_question() -> dict:
    """The steps (in the order they started) and notes of the question that just ended."""
    global _finished
    with _lock:
        rec = _finished or _current
        _finished = None
    if rec is None:
        return {"steps": [], "flags": {}}
    with rec.lock:
        return {"steps": [s for _, s in sorted(rec.steps, key=lambda item: item[0])], "flags": dict(rec.flags)}


def current_recorder() -> Recorder | None:
    """The recorder of the question being run now, or None outside an evaluation run."""
    return _current
