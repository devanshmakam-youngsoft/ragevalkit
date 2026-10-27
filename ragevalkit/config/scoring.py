"""How answers are scored and how the version to ship is chosen."""
from ragevalkit.config.base import Settings


class ScoringSettings(Settings):
    # Recommendation
    answer_weight: float = 0.6
    material_weight: float = 0.4
    recommendation_tolerance: float = 0.25
    max_response_time: float | None = None

    # Text metrics to run
    run_keyword_recall: bool = True
    run_bm25: bool = True
    run_semantic_similarity: bool = True
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
