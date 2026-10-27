"""Finding the guides for the Help page."""
from ragevalkit.exceptions import NotFoundError
from ragevalkit.guides import GUIDES, Guide


def list_guides() -> list[dict]:
    return [{"id": g.guide_id, "title": g.title, "description": g.description} for g in GUIDES]


def find_guide(guide_id: str) -> Guide:
    guide = next((g for g in GUIDES if g.guide_id == guide_id), None)
    if guide is None or not guide.path.is_file():
        raise NotFoundError("Guide not found")
    return guide
