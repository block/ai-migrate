import re
import subprocess
from typing import Literal

from ai_migrate.manifest import Manifest

Status = Literal["pass", "fail", "?"]


def get_branches(
    manifest: Manifest | None = None,
) -> list[tuple[str, str, Status, str]]:
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

    in_manifest = {f.group_name() for f in manifest.files} if manifest else {}
    matching = []
    for line in branches:
        sha, branch, msg = line.split(maxsplit=2)
        if branch.startswith("ai-migrator/"):
            if not in_manifest or branch.removeprefix("ai-migrator/") in in_manifest:
                pattern = r"Migration attempt \d+ status='(.*)':"
                match = re.search(pattern, msg)
                status = match.group(1) if match else "?"
                matching.append((sha, branch, status, msg))

    return matching


def get_worktrees() -> list[tuple[str, str, bool]]:
    result = subprocess.run(
        ["git", "worktree", "list"],
        capture_output=True,
        text=True,
        check=True,
    )
    worktrees = []
    for row in result.stdout.strip().splitlines():
        worktree, sha, branch_with_brackets, *rest = row.split()
        assert branch_with_brackets[0] == "[" and branch_with_brackets[-1] == "]"
        branch = branch_with_brackets[1:-1]
        worktrees.append(
            (
                worktree,
                branch,
                "prunable" in rest,
            )
        )
    return worktrees
