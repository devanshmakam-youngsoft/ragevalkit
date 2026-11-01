"""One log file for one run (or one generation job), plus the list of problems it met."""
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path

from ragevalkit.core.config import Config
from ragevalkit.core.constants.library import LOGGER_NAME
from ragevalkit.core.diagnostics.issues import Issue, make_issue
from ragevalkit.core.diagnostics.redaction import redact

LINE_FORMAT = "%(asctime)s %(levelname)-7s %(message)s"
logger = logging.getLogger(__name__)


def _safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")[:60] or "run"


class EventLog:
    """``<data folder>/logs/<folder>/<time>_<name>.log``: everything that happened, including full tracebacks.

    Lines also reach the server log. A folder that cannot be written to never stops the work: the lines then
    go to the server log only.
    """

    def __init__(self, config: Config, folder: str, name: str):
        self._config = config
        self.issues: list[Issue] = []
        self.issue_total = 0
        self._seen: dict[tuple, Issue] = {}
        self.path: Path | None = None
        self._handler: logging.FileHandler | None = None
        self._logger = logging.getLogger(f"{LOGGER_NAME}.{folder}.{uuid.uuid4().hex[:8]}")
        self._open(config.logs_dir / folder, f"{datetime.now():%Y%m%d-%H%M%S}_{_safe_name(name)}.log")

    def _open(self, directory: Path, file_name: str) -> None:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            self._prune(directory)
            self._handler = logging.FileHandler(directory / file_name, encoding="utf-8")
            self._handler.setFormatter(logging.Formatter(LINE_FORMAT))
            self._logger.addHandler(self._handler)
            self._logger.setLevel(logging.DEBUG)
            self.path = directory / file_name
        except OSError as error:
            logger.warning("Cannot write log files in %s (%s); the server log is used instead.", directory, error)

    def _prune(self, directory: Path) -> None:
        newest_first = sorted(directory.glob("*.log"), key=lambda path: path.stat().st_mtime, reverse=True)
        for path in newest_first[self._config.keep_run_logs:]:
            try:
                path.unlink()
            except OSError:
                pass

    @property
    def file_name(self) -> str | None:
        """The log file's name without its folder, or ``None`` when no file could be opened."""
        return self.path.name if self.path else None

    def info(self, message: str, *args) -> None:
        """Write an INFO line; ``args`` fill ``%`` placeholders in ``message`` and secrets are hidden."""
        self._logger.info(redact(message % args if args else message))

    def warning(self, message: str, *args) -> None:
        """Write a WARNING line; ``args`` fill ``%`` placeholders in ``message`` and secrets are hidden."""
        self._logger.warning(redact(message % args if args else message))

    def issue(self, stage: str, error: BaseException, where: str = "", *, severity: str = "error") -> Issue:
        """Record a problem: the full traceback goes to the log file, a plain message to the dashboard.

        A problem identical to one already recorded (same stage, error type and message start) is not listed
        again; the existing ``Issue`` has its ``count`` raised and is returned. Only the first
        ``max_issues_per_run`` distinct problems are kept in ``issues``; ``issue_total`` counts every distinct one.
        """
        level = logging.ERROR if severity == "error" else logging.WARNING
        same = self._seen.get((stage, type(error).__name__, str(error)[:200]))
        if same is not None:        # a chatbot that is down fails every question the same way: say it once, with a count
            same.count += 1
            self._logger.log(level, "[%s] %s | same problem again (%d times so far)", stage, where or "-", same.count)
            return same
        found = make_issue(stage, error, where, severity, self._config.max_technical_chars)
        self._logger.log(level, "[%s] %s | %s\n%s", stage, where or "-", found.message, found.technical)
        self._seen[(stage, type(error).__name__, str(error)[:200])] = found
        self.issue_total += 1
        if len(self.issues) < self._config.max_issues_per_run:
            self.issues.append(found)
        return found

    def issue_dicts(self) -> list[dict]:
        """Return the recorded problems as dicts, technical detail included."""
        return [found.to_dict() for found in self.issues]

    def close(self) -> None:
        """Stop writing to the log file and release it. Calling it again does nothing."""
        if self._handler is not None:
            self._logger.removeHandler(self._handler)
            self._handler.close()
            self._handler = None
