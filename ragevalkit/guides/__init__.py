"""The guides shown in the dashboard's Help page: standalone HTML pages that ship inside the package."""
from dataclasses import dataclass
from pathlib import Path

GUIDES_DIR = Path(__file__).parent


@dataclass(frozen=True)
class Guide:
    guide_id: str
    title: str
    description: str
    file_name: str

    @property
    def path(self) -> Path:
        return GUIDES_DIR / self.file_name


GUIDES = [
    Guide("developer-guide", "Developer guide",
          "Connect your pipeline, every serve() option, step recording, test cases and reading the results.",
          "developer-guide.html"),
    Guide("how-it-works", "How ragevalkit works",
          "What happens during a run, how scores are made, and where each part of the code lives.",
          "how-it-works.html"),
]

__all__ = ["GUIDES", "GUIDES_DIR", "Guide"]
