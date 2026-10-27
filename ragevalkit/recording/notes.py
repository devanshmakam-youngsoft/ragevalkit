"""``note()``: free-form flags attached to the question being evaluated."""
from ragevalkit.recording.limits import display_text
from ragevalkit.recording.recorder import current_recorder
from ragevalkit.recording.redaction import is_secret_name


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
    rec = current_recorder()
    if rec is not None and rec.open and not is_secret_name(key):
        with rec.lock:
            rec.flags[key] = display_text(value)
