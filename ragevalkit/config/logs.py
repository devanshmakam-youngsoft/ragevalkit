"""Log files: how big they get and how many problems one run reports."""
from ragevalkit.config.base import Settings


class LogSettings(Settings):
    log_level: str = "INFO"
    server_log_max_mb: int = 5          # server.log is rotated at this size
    server_log_backups: int = 3         # how many rotated copies of server.log are kept
    keep_run_logs: int = 200            # newest logs kept per folder (runs, generation); older ones are deleted
    max_issues_per_run: int = 100       # problems listed per run; the log file has all of them
    max_technical_chars: int = 2000     # longest technical detail kept with a problem (the end of a traceback)
