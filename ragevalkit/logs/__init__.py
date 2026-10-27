"""Log files and plain-language problem reports.

``configure_logging`` sets up ``eval_logs/server.log``; ``EventLog`` writes one file per evaluation run or
generation job; ``Issue`` is a problem with a message for people and technical detail for whoever needs it.
"""
from ragevalkit.logs.event_log import EventLog
from ragevalkit.logs.issues import Issue
from ragevalkit.logs.plain_language import explain
from ragevalkit.logs.redaction import redact
from ragevalkit.logs.setup import configure_logging

__all__ = ["EventLog", "Issue", "configure_logging", "explain", "redact"]
