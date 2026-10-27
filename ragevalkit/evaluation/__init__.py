"""
RunManager — the evaluation engine.

EXECUTION MODEL
---------------
Every call to RunManager.start() launches a daemon thread named "eval-{version}".
The HTTP response returns immediately (202 Accepted) while the thread works.
Progress is published via run.events (a plain list) which the SSE endpoint
streams to the dashboard by polling it every 0.3 s.

WHY a daemon thread (not asyncio)?
  The developer's fn() may block for seconds (LLM calls, DB queries).
  A daemon thread can block freely without stalling the FastAPI event loop.
  daemon=True means the thread is killed automatically if the server exits.

CALL FLOW (one question)
------------------------
  _execute()
    └─ _process_row()
         ├─ _call_fn()             ← calls developer's fn(); recording captures steps + flags
         ├─ check_sources_by_keyword()        ← compares expected_sources against recorded sources (if column present)
         ├─ lexical metrics        ← keyword_recall, bm25_score, semantic_similarity
         ├─ extra_metrics          ← any custom metric fns passed to serve()
         └─ _grade()              ← LLM judge or custom judge_fn

SIGNATURE DETECTION
-------------------
detect_call_style() inspects the developer's function ONCE at startup (not per call).
It checks parameter names against configurable alias sets and caches the
result so every question pays zero inspection cost at eval time.

HISTORY FORMAT
--------------
Internally history is always stored as [{"question": ..., "answer": ...}].
format_history() converts to the format the developer's fn expects
("dict" stays as-is; "openai" → [{"role": "user", ...}, {"role": "assistant", ...}]).

STOP A RUNNING EVAL
-------------------
POST /api/runs/{run_id}/stop sets Run.stop_requested = True.
The _execute() loop checks this flag at the start of each row iteration.
When triggered, it finalises the partial results (writes them to store) and
emits a "stopped" event.

QUESTION FINGERPRINTING
-----------------------
The dataset's question set is hashed on load and stored in the run summary as
question_fingerprint. The dashboard can compare fingerprints across versions to
warn when questions changed between runs.
"""
from ragevalkit.evaluation.exceptions import RunBusy, RunError
from ragevalkit.evaluation.run import Run
from ragevalkit.evaluation.runner import RunManager

__all__ = ["Run", "RunBusy", "RunError", "RunManager"]
