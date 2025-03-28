from abc import ABC, abstractmethod
from typing import Any


class BaseLLMClient(ABC):
    """Base class for all LLM clients that defines the standard interface."""

    @abstractmethod
    async def generate_completion(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.1,
        max_tokens: int = 8192,
        model: str | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Generate a completion from the LLM.

        Args:
            messages: The messages to send to the LLM
            tools: Optional tools to provide to the LLM
            temperature: The temperature to use for generation
            max_tokens: The maximum number of tokens to generate
            model: Optional model override

        Returns:
            A tuple of (response, messages)
        """
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    def count_tokens(self, text_or_messages: str | list[dict[str, Any]]) -> int:
        pass

    @abstractmethod
    def max_context_tokens(self) -> int:
        """Get the maximum context size for the model.

        Returns:
            The maximum number of tokens the model can handle
            -1 means no limit
        """
        pass
