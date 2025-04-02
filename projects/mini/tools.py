from pydantic_ai import Tool

from ai_migrate.context import ToolCallContext


def add(ctx: ToolCallContext, x: int, y: int) -> int:
    """Add two numbers"""
    return x + y


tools = [Tool(add)]
