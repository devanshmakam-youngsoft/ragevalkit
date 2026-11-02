"""The model that writes test cases."""
from ragevalkit.services.llm_client import complete


class GenerationModelClient:
    """The model that writes test cases: ``generator_model`` if set, otherwise the judge's model.

    Both are called with the judge's API key (``judge_api_key``); there is no separate generator key.
    """

    def __init__(self, config):
        self.config = config

    @property
    def model(self) -> str:
        """The model name sent to LiteLLM, for example ``groq/openai/gpt-oss-120b``."""
        return self.config.generator_model or self.config.judge_model

    def __call__(self, messages: list[dict]) -> str:
        """Send the chat ``messages`` to the model, asking for JSON, and return its reply text."""
        return complete(messages, model=self.model, api_key=self.config.judge_api_key, json_mode=True)
