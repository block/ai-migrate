import tiktoken
from typing import Any

from openai import AsyncOpenAI
from pydantic_ai.tools import ToolDefinition

GPT_VERSION = "gpt-4o"


def _tool(tool: ToolDefinition) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters_json_schema,
        },
    }


class OpenAIClient:
    """A client for interacting with a large language model."""

    def __init__(self):
        self._openai_client = AsyncOpenAI()

    async def generate_completion(
        self,
        messages: list[dict[str, str]],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.1,
        max_tokens: int = 8192,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Generate a completion

        Args:
            messages: The messages to send
            tools: Optional tools to provide
            temperature: The temperature to use for generation
            max_tokens: The maximum number of tokens to generate

        Returns:
            A tuple of (response, messages)
        """
        response = await self._openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=temperature,
            tools=[_tool(t) for t in tools or []],
            max_tokens=max_tokens,
        )
        response = response.model_dump()

        return response, messages

    async def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
    ) -> str:
        """Generate text with a simple system and user prompt.

        Args:
            system_prompt: The system prompt
            user_prompt: The user prompt
            temperature: The temperature to use for generation

        Returns:
            The generated text
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response, _ = await self.generate_completion(messages, temperature=temperature)
        return response["choices"][0]["message"]["content"]

    def count_tokens(self, text: str | list[dict[str, Any]] | None) -> int:
        if not text:
            return 0
        elif isinstance(text, str):
            return len(tiktoken.encoding_for_model(GPT_VERSION).encode(text))
        elif isinstance(text, list):
            return sum(self.count_tokens(item.get("content")) for item in text)
        else:
            raise ValueError(f"Unsupported text type: {type(text)}")

    def max_context_tokens(self) -> int:
        """Get the maximum context size for the model. -1 means no limit."""
        return -1
