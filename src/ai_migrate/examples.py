import glob
import json
import re
from pathlib import Path
import subprocess


def get_git_file_content(file: str, ref: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{ref}:{file}"],
        capture_output=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode()
        if re.match(
            r"fatal: path '.*' exists on disk, but not in '[a-f0-9+]'",
            stderr,
        ) or re.match(
            r"fatal: path '.*' does not exist in '[a-f0-9+]'",
            stderr,
        ):
            return None
    return result.stdout.decode()


def path_to_name(path: Path | str) -> str:
    return str(path).replace("/", "__")


def setup_from_pr(pr_num, examples_dir, pattern=None) -> None:
    default_branch = (
        subprocess.run(
            [
                "git",
                "rev-parse",
                "--abbrev-ref",
                "origin/HEAD",
            ],
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .strip()
    )

    output = subprocess.run(
        [
            "gh",
            "pr",
            "view",
            str(pr_num),
            "--json",
            "mergeCommit,headRefOid",
        ],
        capture_output=True,
        check=True,
    ).stdout.decode()
    out = json.loads(output)
    merge_commit = out.get("mergeCommit")
    if merge_commit:
        ref = merge_commit["oid"]
    else:
        ref = out["headRefOid"]

    subprocess.run(["git", "fetch"], check=True)

    prev_ref = (
        subprocess.run(
            ["git", "merge-base", default_branch, f"{ref}~"],
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .strip()
    )

    return setup(ref, prev_ref, examples_dir, pattern)


def setup(ref, ref_prev=None, examples_dir="examples", pattern=None) -> None:
    ref = str(ref)
    if ref_prev is None:
        ref_prev = f"{ref}~"
    files = (
        subprocess.run(
            [
                "git",
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                f"{ref}..{ref_prev}",
            ],
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .splitlines()
    )
    if pattern:
        files = [file for file in files if glob.fnmatch.fnmatch(file, pattern)]

    out_dir = Path(examples_dir)
    i = 0
    taken = set(o.name for o in out_dir.iterdir())
    while (f"group{i}.new" in taken) or (f"group{i}.old" in taken):
        i += 1

    group_name = f"group{i}"

    for suffix in ("new", "old"):
        d = out_dir / f"{group_name}.{suffix}"
        d.mkdir()

    for file in files:
        for get_ref, ext in (
            (ref, "new"),
            (ref_prev, "old"),
        ):
            content = get_git_file_content(file, get_ref)
            if content:
                out_file = out_dir / f"{group_name}.{ext}" / path_to_name(file)
                out_file.write_text(content)
