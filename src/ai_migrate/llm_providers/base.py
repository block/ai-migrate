from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Union


class BaseLLMClient(ABC):
    """Base class for all LLM clients that defines the standard interface."""

    @abstractmethod
    async def generate_completion(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.1,
        max_tokens: int = 8192,
        model: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
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
    def count_tokens(self, text_or_messages: Union[str, List[Dict[str, Any]]]) -> int:
        """Count tokens in a message list or string.

        Args:
            text_or_messages: Either a list of messages or a string

        Returns:
            The token count
        """
        pass

    @abstractmethod
    def max_context_tokens(self) -> int:
        """Get the maximum context size for the model.

        Returns:
            The maximum number of tokens the model can handle
            -1 means no limit
        """
        pass
