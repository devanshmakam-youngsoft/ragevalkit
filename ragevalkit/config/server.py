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

    @property
    def inputs_dir(self) -> Path:
        return self.store_path.parent / "eval_inputs"
