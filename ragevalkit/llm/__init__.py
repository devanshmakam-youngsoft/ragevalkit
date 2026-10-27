"""Calling language models through LiteLLM: a safe one-time load and a single ``complete()`` call."""
from ragevalkit.llm.completion import complete
from ragevalkit.llm.loader import load_litellm

__all__ = ["complete", "load_litellm"]
