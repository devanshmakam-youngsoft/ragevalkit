"""How answers are scored and how the version to ship is chosen."""
from ragevalkit.core.config.base import Settings


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
    run_semantic_similarity: bool = True
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
