"""``Config``: every option of the library, assembled from the settings groups in this package."""
from ragevalkit.core.config.access import AccessSettings
from ragevalkit.core.config.datasets import DatasetSettings
from ragevalkit.core.config.function_adapter import FunctionAdapterSettings
from ragevalkit.core.config.generation import GenerationSettings
from ragevalkit.core.config.judge import JudgeSettings
from ragevalkit.core.config.logs import LogSettings
from ragevalkit.core.config.recording import RecordingSettings
from ragevalkit.core.config.scoring import ScoringSettings
from ragevalkit.core.config.server import ServerSettings


class Config(
    ServerSettings,
    LogSettings,
    AccessSettings,
    RecordingSettings,
    JudgeSettings,
    GenerationSettings,
    ScoringSettings,
    FunctionAdapterSettings,
    DatasetSettings,
):
    """All options with their defaults. ``serve()`` fills it from its arguments."""
