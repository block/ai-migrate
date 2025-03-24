from importlib.metadata import entry_points

from .openai import OpenAIClient

try:
    DefaultClient = entry_points(group="ai_migrate")["default_llm_provider"].load()
except KeyError:
    DefaultClient = OpenAIClient
