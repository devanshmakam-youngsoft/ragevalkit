"""The guide shown on the dashboard's Help page: one standalone HTML page that ships inside the package."""
from pathlib import Path

GUIDE_PATH = Path(__file__).parent / "developer-guide.html"

__all__ = ["GUIDE_PATH"]
