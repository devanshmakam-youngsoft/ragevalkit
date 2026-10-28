"""Where the server runs and where results are kept."""
from pathlib import Path

from ragevalkit.config.base import Settings


class ServerSettings(Settings):
    # Environment mode
    # "dev"  — full dashboard + eval routes (default)
    # "uat"  — same as dev, but logs that UAT recording is active (no extra endpoint)
    # "prod" — blocks dashboard and all eval routes; only /api/health responds
    eval_env: str = "dev"

    backend_host: str = "127.0.0.1"
    backend_port: int = 8001

    store_path: Path = Path("eval_store.json")

    # Show the Help page (the guide) in the dashboard
    show_guide: bool = True

    # Folder for log files; empty means "eval_logs" beside the results store
    log_dir: Path | None = None

    @property
    def inputs_dir(self) -> Path:
        return self.store_path.parent / "eval_inputs"

    @property
    def logs_dir(self) -> Path:
        return self.log_dir or self.store_path.parent / "eval_logs"
