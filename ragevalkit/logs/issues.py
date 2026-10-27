"""A problem found while something ran: a plain message for the dashboard, technical detail on request."""
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from ragevalkit.logs.plain_language import explain
from ragevalkit.logs.redaction import redact


@dataclass
class Issue:
    stage: str          # which part of the run: "answer", "grading", "summary", ...
    where: str          # which question or file, in words
    message: str        # plain language, safe to show anyone
    technical: str      # the exception and the end of its traceback, secrets hidden
    severity: str       # "error": something is missing or wrong; "warning": it carried on with a fallback
    at: str
    count: int = 1      # how many times this same problem happened

    def to_dict(self) -> dict:
        return asdict(self)

    def without_technical(self) -> dict:
        return {key: value for key, value in self.to_dict().items() if key != "technical"}


def technical_text(error: BaseException, max_chars: int) -> str:
    """``ErrorType: message`` and the traceback, with secrets hidden. Only the end is kept when it is long."""
    text = redact("".join(traceback.format_exception(type(error), error, error.__traceback__)).strip())
    return text if len(text) <= max_chars else "…" + text[-max_chars:]


def make_issue(stage: str, error: BaseException, where: str, severity: str, max_technical_chars: int) -> Issue:
    return Issue(
        stage=stage, where=where, message=explain(error, stage),
        technical=technical_text(error, max_technical_chars), severity=severity,
        at=datetime.now(timezone.utc).isoformat(),
    )
