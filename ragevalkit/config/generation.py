"""Writing test cases from uploaded documents."""
from ragevalkit.config.base import Settings


class GenerationSettings(Settings):
    # Model that writes the questions; empty means "use judge_model". Document text is sent to it.
    generator_model: str = ""
    generate_max_files: int = 5
    generate_max_file_mb: int = 50
    generate_per_category_max: int = 10
    generate_workers: int = 4          # questions written in parallel
    batch_ttl_hours: int = 24          # generated questions not approved within this time are deleted
