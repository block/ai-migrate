from itertools import cycle
from pathlib import Path
from typing import Any, Dict, List, Union


class FakeLLMClient:
    def __init__(self, directory):
        self.responses = cycle([f.read_text() for f in Path(directory).iterdir()])

    async def generate_completion(
        self, messages, tools=None, temperature=0.0, max_tokens=0
    ):
        response_body = next(self.responses)
        return {"choices": [{"message": {"content": response_body}}]}, messages

    def count_tokens(self, text: Union[str, List[Dict[str, Any]]]) -> int:
        if isinstance(text, str):
            return len(text)
        elif isinstance(text, list):
            return sum(self.count_tokens(item["content"]) for item in text)
        else:
            raise ValueError(f"Unsupported text type: {type(text)}")

    def max_context_tokens(self) -> int:
        return -1
