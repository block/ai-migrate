from itertools import cycle
from pathlib import Path


class FakeLLMClient:
    def __init__(self, directory):
        self.responses = cycle([f.read_text() for f in Path(directory).iterdir()])

    async def generate_completion(
        self, messages, tools=None, temperature=0.0, max_tokens=0
    ):
        response_body = next(self.responses)
        return {"choices": [{"message": {"content": response_body}}]}, messages
