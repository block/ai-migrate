from importlib.metadata import entry_points

from .openai import OpenAIClient
from .base import BaseLLMClient

try:
    DefaultClient = entry_points(group="ai_migrate")["default_llm_provider"].load()
except KeyError:
    DefaultClient = OpenAIClient

__all__ = ["BaseLLMClient", "DefaultClient", "OpenAIClient"]
