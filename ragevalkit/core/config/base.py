"""The settings base class every group of options builds on."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Reads values from serve() arguments and from a ``.env`` file; unknown keys are ignored."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
