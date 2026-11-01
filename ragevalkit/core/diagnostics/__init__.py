"""Log files and plain-language problem reports.

``configure_logging`` sets up ``<data folder>/logs/server.log``; ``EventLog`` writes one file per evaluation run or
generation job; ``Issue`` is a problem with a message for people and technical detail for whoever needs it.
"""
from ragevalkit.core.diagnostics.event_log import EventLog
from ragevalkit.core.diagnostics.issues import Issue
from ragevalkit.core.diagnostics.plain_language import explain
from ragevalkit.core.diagnostics.redaction import redact
from ragevalkit.core.diagnostics.setup import configure_logging

__all__ = ["EventLog", "Issue", "configure_logging", "explain", "redact"]
