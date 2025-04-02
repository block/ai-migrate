from dataclasses import dataclass
from pathlib import Path

from pydantic_ai import RunContext


@dataclass
class MigrationContext:
    target_files: list[str]
    target_dir: Path | None


ToolCallContext = RunContext[MigrationContext]
