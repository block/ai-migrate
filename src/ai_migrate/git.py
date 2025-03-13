import re
import subprocess
from typing import Literal

Status = Literal["pass", "fail", "?"]


def get_branches() -> list[tuple[str, str, Status, str]]:
    result = subprocess.run(
        [
            "git",
            "branch",
            "--format=%(objectname:short) %(refname:short) %(contents:lines=1)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    branches = result.stdout.strip().split("\n")

    matching = []
    for line in branches:
        sha, branch, msg = line.split(maxsplit=2)
        if branch.startswith("ai-migrator/"):
            pattern = r"Migration attempt \d+ status='(.*)':"
            match = re.search(pattern, msg)
            status = match.group(1) if match else "?"
            matching.append((sha, branch, status, msg))

    return matching
