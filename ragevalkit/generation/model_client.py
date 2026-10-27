"""The model that writes test cases."""
from ragevalkit.llm import complete


class GenerationModelClient:
    """The configured model: ``generator_model`` if set, otherwise the judge's model, through GenerationModelClient."""

    def __init__(self, config):
        self.config = config

    @property
    def model(self) -> str:
        return self.config.generator_model or self.config.judge_model

    def __call__(self, messages: list[dict]) -> str:
        return complete(messages, model=self.model, api_key=self.config.judge_api_key, json_mode=True)
