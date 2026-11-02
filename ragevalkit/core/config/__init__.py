"""Library configuration: one small file per group of options, assembled into ``Config``."""
from ragevalkit.core.config.dotenv import load_dotenv
from ragevalkit.core.config.settings import Config

__all__ = ["Config", "load_dotenv"]
