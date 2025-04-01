import json
from itertools import cycle
from pathlib import Path
from typing import Any


class FakeLLMClient:
    def __init__(self, directory):
        responses = []
        for f in sorted(Path(directory).iterdir()):
            content = f.read_text()
            if f.suffix == ".json":
                content = json.loads(content)
            responses.append(content)
        self.responses = cycle(responses)

    async def generate_completion(
        self, messages, tools=None, temperature=0.0, max_tokens=0
    ):
        response = next(self.responses)
        if isinstance(response, dict):
            return response, messages
        return {"choices": [{"message": {"content": response}}]}, messages

    def count_tokens(self, text: str | list[dict[str, Any]]) -> int:
        if isinstance(text, str):
            return len(text)
        elif isinstance(text, list):
            return sum(self.count_tokens(item["content"]) for item in text)
        else:
            raise ValueError(f"Unsupported text type: {type(text)}")

    def max_context_tokens(self) -> int:
        return -1
