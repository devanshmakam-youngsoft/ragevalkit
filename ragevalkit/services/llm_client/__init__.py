"""Calling language models through LiteLLM: a safe one-time load and a single ``complete()`` call."""
from ragevalkit.services.llm_client.completion import complete
from ragevalkit.services.llm_client.loader import load_litellm

__all__ = ["complete", "load_litellm"]
