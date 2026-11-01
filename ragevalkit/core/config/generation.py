"""Writing test cases from uploaded documents."""
from ragevalkit.core.config.base import Settings


class GenerationSettings(Settings):
    """Options for writing test cases from uploaded documents: model, upload limits and batch lifetime."""

    # Model that writes the questions; empty means "use judge_model". Document text is sent to it.
    generator_model: str = ""
    generate_max_files: int = 5        # documents accepted per generation request
    generate_max_file_mb: int = 50     # largest single document, in megabytes
    generate_per_category_max: int = 10  # most questions a request may ask for in one category
    generate_workers: int = 4          # questions written in parallel
    batch_ttl_hours: int = 24          # generated questions not approved within this time are deleted
