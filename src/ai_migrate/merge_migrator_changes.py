import subprocess
from pathlib import Path

from ai_migrate.git import get_branches
from ai_migrate.manifest import Manifest


def merge(manifest_file: str):
    manifest = Manifest.model_validate_json(Path(manifest_file).read_text())
    matching_branches = [
        (branch, status) for _, branch, status, _ in get_branches(manifest)
    ]
    mergeable = [b for b, status in matching_branches if status == "pass"]
    print("Merging:")
    print("\n".join(mergeable))
    print("Ignoring:\n")
    print(
        "\n".join(
            f"{b} ({status})" for b, status in matching_branches if b not in mergeable
        ),
    )

    if not matching_branches:
        raise ValueError("No matching branches")

    subprocess.run(["git", "merge", "--squash", *mergeable], check=True)


if __name__ == "__main__":
    merge()
