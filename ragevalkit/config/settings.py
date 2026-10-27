"""``Config``: every option of the library, assembled from the settings groups in this package."""
from ragevalkit.config.access import AccessSettings
from ragevalkit.config.datasets import DatasetSettings
from ragevalkit.config.function_adapter import FunctionAdapterSettings
from ragevalkit.config.generation import GenerationSettings
from ragevalkit.config.judge import JudgeSettings
from ragevalkit.config.logs import LogSettings
from ragevalkit.config.recording import RecordingSettings
from ragevalkit.config.scoring import ScoringSettings
from ragevalkit.config.server import ServerSettings


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
