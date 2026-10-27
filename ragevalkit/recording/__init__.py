"""
Step recording — the zero-overhead observability layer for ragevalkit.

HOW IT WORKS
------------
`ragevalkit.step("name")` returns a StepContext that does nothing at all
unless the current thread is inside an active eval run.

When the RunManager calls the developer's function it:
  1. calls begin_question(detail)  → sets this thread's "active" flag + clears the step/flag buffers
  2. calls fn(question)       → developer code runs; any @step / with step: fires _emit()
  3. calls end_question()      → clears the active flag  (in a finally block — always runs)
  4. calls collect_question()         → drains the buffers and returns {"steps": [...], "flags": {...}}

WHY a recorder per question, not per thread
------------------------------------------
The runner handles ONE question at a time (and one run at a time), so everything recorded while ``fn()`` is
running belongs to that question, whichever thread records it. Pipelines often search several indexes in a
thread pool, or hand work to an executor; a step started there still lands in the current question's recorder.
Each step takes hold of its recorder when it STARTS, so a slow leftover thread from question 1 can never add
its step to question 2: once a question is collected its recorder is closed and late steps are ignored.

WHY end_question() is in a finally block in runner.py
-----------------------------------------------------
If fn() raises an exception the finally block still closes the recorder, so the next question's
begin_question() starts with a clean slate rather than accumulating stale steps from a failed call.

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
from ragevalkit.recording.limits import LIMITS, clip_material, configure, display_text
from ragevalkit.recording.notes import note
from ragevalkit.recording.recorder import begin_question, collect_question, end_question
from ragevalkit.recording.steps import step

__all__ = [
    "LIMITS", "begin_question", "clip_material", "collect_question", "configure", "display_text",
    "end_question", "note", "step",
]
