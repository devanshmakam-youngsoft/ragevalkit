"""How answers are scored and how the version to ship is chosen."""
import importlib.util
from functools import cache

from ragevalkit.core.config.base import Settings
from ragevalkit.core.constants import LIBRARY_NAME

SEMANTIC_INSTALL_COMMAND = f'pip install "{LIBRARY_NAME}[semantic]"'


@cache
def semantic_extra_installed() -> bool:
    """Whether the optional ``semantic`` extra (``sentence-transformers``) is installed, without importing it."""
    return importlib.util.find_spec("sentence_transformers") is not None


class ScoringSettings(Settings):
    """Options for the built-in text metrics and for the weights used to recommend a version."""

    # Recommendation
    answer_weight: float = 0.6                  # share of answer_marks in the overall score
    material_weight: float = 0.4                # share of material_marks; 0 for systems without retrieval
    recommendation_tolerance: float = 0.25      # versions this close to the best overall score count as tied
    recommendation_min_quality: float = 5.0     # below this overall score (0-10) nothing is recommended
    max_response_time: float | None = None      # seconds; slower versions are not recommended

    # Text metrics to run
    run_keyword_recall: bool = True
    run_bm25: bool = True
    run_semantic_similarity: bool | None = None   # None: on when the optional `semantic` extra is installed, else off
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    @property
    def semantic_similarity_enabled(self) -> bool:
        """Whether the meaning score is computed: the option when it was set, else whether the extra is installed."""
        if self.run_semantic_similarity is None:
            return semantic_extra_installed()
        return self.run_semantic_similarity
