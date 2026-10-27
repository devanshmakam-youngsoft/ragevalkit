"""What ``step()`` and ``note()`` capture while your pipeline runs."""
from ragevalkit.config.base import Settings


class RecordingSettings(Settings):
    # Recording mode (controls what @step captures during eval runs)
    # "eval"     — record steps only during eval runner calls (default)
    # "uat"      — reserved; behaves like "eval"
    # "off"      — disable all step recording (eval still runs, just no step data)
    record_mode: str = "eval"

    # Recording detail level (controls HOW MUCH is captured per step)
    # "all"      — inputs, outputs, material, sources, timing (default)
    # "selected" — only steps where developer explicitly set .material or .sources
    # "off"      — only step name + elapsed time (no content captured)
    record_detail: str = "all"

    # How much of a step is kept. Shown inputs, outputs and notes are cut at step_value_chars; the material the
    # judge reads is cut at material_chars. A cut always ends with a marker saying how much was left out.
    step_value_chars: int = 1000
    material_chars: int = 20000
