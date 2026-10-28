"""The guide for the Help page, and which optional parts of the dashboard are switched on."""
from ragevalkit.config import Config
from ragevalkit.exceptions import NotFoundError
from ragevalkit.guides import GUIDE_PATH


def guide_page(cfg: Config) -> str:
    if not cfg.show_guide or not GUIDE_PATH.is_file():
        raise NotFoundError("Guide not found")
    return GUIDE_PATH.read_text(encoding="utf-8")


def enabled_features(cfg: Config) -> dict:
    """What the dashboard may show: the Help link appears only when the guide is on."""
    return {"guide": cfg.show_guide and GUIDE_PATH.is_file()}
