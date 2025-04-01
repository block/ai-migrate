from pydantic_ai import Tool


def add(x: int, y: int) -> int:
    """Add two numbers"""
    return x + y


tools = [Tool(add)]
