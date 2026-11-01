"""Loading litellm without tripping over itself.

litellm takes seconds to import, and it loads parts of itself lazily: the first log record after it is loaded
makes its logging filter import more modules. When two threads do this at the same moment (a worker calling the
model while the web server logs a request) Python reports "deadlock detected by _ModuleLock" or hands out a
half-loaded module with "no attribute 'completion'". ``load_litellm`` finishes all of it, once, under a lock;
``serve`` calls it at start-up, before any other thread exists.
"""
from __future__ import annotations

import importlib
import threading

_lock = threading.Lock()


_LAZY_PARTS = ("litellm.rust_bridge.diagnostics", "litellm.rust_bridge.catalog")   # imported on first log record


def load_litellm():
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
