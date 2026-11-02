"""Where the server runs and where results are kept."""
from pathlib import Path

from ragevalkit.core.config.base import Settings
from ragevalkit.core.constants import (
    DATA_DIR_NAME,
    LOGS_DIR_NAME,
    STORE_FILE_NAME,
    UPLOADS_DIR_NAME,
)


class ServerSettings(Settings):
    """Options for the HTTP server: environment mode, address, data folder and the paths derived from it."""

    # Environment mode
    # "dev"  — full dashboard + eval routes (default)
    # "uat"  — same as dev, but logs that UAT recording is active (no extra endpoint)
    # "prod" — blocks dashboard and all eval routes; only /api/health responds
    eval_env: str = "dev"

    backend_host: str = "127.0.0.1"
    backend_port: int = 8001

    # Everything the library writes lives in this one folder: the store, the logs and the uploads
    data_dir: Path = Path(DATA_DIR_NAME)

    # Show the Help page (the guide) in the dashboard
    show_guide: bool = True

    @property
    def store_path(self) -> Path:
        """The JSON file holding results, test cases and groups."""
        return self.data_dir / STORE_FILE_NAME

    @property
    def logs_dir(self) -> Path:
        """The folder with ``server.log`` and the per-run and per-generation logs."""
        return self.data_dir / LOGS_DIR_NAME

    @property
    def uploads_dir(self) -> Path:
        """The folder where spreadsheets uploaded for a run are saved."""
        return self.data_dir / UPLOADS_DIR_NAME
