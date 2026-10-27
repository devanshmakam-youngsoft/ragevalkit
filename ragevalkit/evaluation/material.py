"""Choosing which recorded steps supply the retrieved text the judge reads."""
import logging

from ragevalkit import recording

logger = logging.getLogger(__name__)


_warned_undeclared_material = False


def select_material(steps: list[dict]) -> str:
    """The retrieved text the judge scores: what steps DECLARED as material (``s.material = …`` or
    ``@step(..., material=True)``). If no step declared any, the output of decorated steps is used, as earlier
    versions did, and a warning explains how to say which step is the retrieval."""
    global _warned_undeclared_material
    declared = [s for s in steps if s.get("material_declared")]
    pool = declared or [s for s in steps if s.get("material")]
    if not declared and len(pool) > 1 and not _warned_undeclared_material:
        _warned_undeclared_material = True
        logger.warning(
            "No step declared its material, so the output of every decorated step (%s) is used as the retrieved "
            "context, including steps that are not retrieval. Mark the retrieval step with "
            "@ragevalkit.step(\"retrieval\", material=True) (or set s.material inside a `with` block) so only it counts.",
            ", ".join(s["name"] for s in pool),
        )
    return recording.clip_material("\n\n".join(s["material"] for s in pool if s.get("material")))
