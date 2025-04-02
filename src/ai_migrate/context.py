from dataclasses import dataclass

from pydantic_ai import RunContext


@dataclass
class MigrationContext:
    target_files: list[str]


ToolCallContext = RunContext[MigrationContext]
