"""Where the library's own log lines go: the console, and ``server.log`` beside the results store."""
import logging
from logging.handlers import RotatingFileHandler

from ragevalkit.config import Config
from ragevalkit.logs.event_log import LINE_FORMAT

LOGGER_NAME = "ragevalkit"
_OURS = "_ragevalkit_handler"
BYTES_PER_MB = 1024 * 1024
logger = logging.getLogger(__name__)


def configure_logging(config: Config) -> None:
    """Show the library's log lines on the console and, outside ``prod``, keep them in ``server.log``.

    Safe to call again: handlers added by an earlier call are replaced.
    """
    package_logger = logging.getLogger(LOGGER_NAME)
    for handler in [h for h in package_logger.handlers if getattr(h, _OURS, False)]:
        package_logger.removeHandler(handler)
        handler.close()
    package_logger.setLevel(config.log_level.upper())

    new_handlers: list[logging.Handler] = []
    if not logging.getLogger().handlers:        # the host application has its own logging: do not print twice
        new_handlers.append(logging.StreamHandler())
    if config.eval_env != "prod":
        try:
            config.logs_dir.mkdir(parents=True, exist_ok=True)
            new_handlers.append(RotatingFileHandler(
                config.logs_dir / "server.log", maxBytes=config.server_log_max_mb * BYTES_PER_MB,
                backupCount=config.server_log_backups, encoding="utf-8",
            ))
        except OSError as error:
            logger.warning("Cannot write %s (%s); logging to the console only.", config.logs_dir, error)
    for handler in new_handlers:
        handler.setFormatter(logging.Formatter(LINE_FORMAT))
        setattr(handler, _OURS, True)
        package_logger.addHandler(handler)
