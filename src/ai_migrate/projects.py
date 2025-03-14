import asyncio
import re
import subprocess
import traceback
from datetime import datetime
from pathlib import Path
import sys
from typing import Iterable

from ai_migrate.git import get_branches
from .manifest import (
    FileEntry,
    Manifest,
    SYSTEM_PROMPT_FILE,
    VERIFY_SCRIPT_FILE,
    FileGroup,
)
from .migrate import run as run_migration, SYSTEM_MESSAGE, FailedPreVerification
from .progress import StatusManager


def get_git_sha(directory: str | Path) -> str:
    """Get the git SHA for HEAD of the repo in the current directory"""
    res = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(directory),
        check=True,
        capture_output=True,
    )
    return res.stdout.decode().strip()


def normalize_file_group(file_or_group: FileEntry | FileGroup) -> FileGroup:
    if isinstance(file_or_group, FileGroup):
        return file_or_group
    return FileGroup(
        files=[file_or_group.filename],
        result=file_or_group.result,
    )


def manifest_from_git() -> Manifest:
    files = []
    for _sha, branch, status, _msg in get_branches():
        file_name = branch.split("/", maxsplit=1)[1].replace("__", "/")
        files.append(FileEntry(filename=file_name, result=status))
    return Manifest(files=files)


def merge_manifests(manifest1: Manifest, manifest2: Manifest):
    entries = {f.group_name(): f for f in manifest1.files}
    for f in manifest2.files:
        if f.result == "pass" and f.group_name() in entries:
            entries[f.group_name()].result = "pass"
    return manifest1.model_copy(update={"files": list(entries.values())})


async def run(
    project_dir: str,
    logs_dir: str | Path,
    manifest_file: str | None,
    files: list[str] | None,
    only_failed: bool,
    max_workers: int = 8,
    local_worktrees=False,
    resume: bool = True,
    llm_fakes=None,
) -> list[FileGroup]:
    """Run an AI migration project."""
    if manifest_file:
        with open(manifest_file) as f:
            manifest = Manifest.model_validate_json(f.read())
    else:
        manifest = Manifest(files=[])

    if resume:
        git_manifest = manifest_from_git()
        manifest = merge_manifests(manifest, git_manifest)

    my_sha = get_git_sha(Path(__file__).parent)
    target_sha = None

    results: list[FileGroup] = []
    if files:
        file_list = [FileGroup(files=[f], result="?") for f in files]
    else:
        file_list = [normalize_file_group(f) for f in manifest.files]

    if not file_list:
        print(
            "No files to migrate. Provide a non-empty manifest or specify files on the command line. "
            "Use the create_manifest command to set up an initial file manifest."
        )
        return []

    if only_failed:
        file_list = [f for f in file_list if f.result != "pass"]

    logs_dir = Path(logs_dir)

    status_manager = StatusManager()

    async def process_one_fileset(index, files: FileGroup, task_name: str):
        nonlocal target_sha
        if target_sha is None:
            target_sha = get_git_sha(Path(files.files[0]).parent)

        await status_manager.update_message(task_name, "Running...")

        log_file = (logs_dir / task_name).with_suffix(".log")
        log_file.parent.mkdir(parents=True, exist_ok=True)

        log_buffer = open(log_file, "w")
        try:
            await run_migration(
                files.files,
                manifest.system_prompt.format(project_dir=project_dir),
                Path(project_dir) / "examples",
                verify_cmd=manifest.verify_cmd.format(
                    project_dir=project_dir, py=sys.executable
                ),
                pre_verify_cmd=manifest.pre_verify_cmd.format(
                    project_dir=project_dir, py=sys.executable
                ),
                log_stream=log_buffer,
                local_worktrees=local_worktrees,
                llm_fakes=llm_fakes,
            )
            new_result = "pass"
            await status_manager.mark_passed(task_name)
        except FailedPreVerification:
            await status_manager.mark_failed(task_name)
            new_result = "fail-pre-verify"
        except Exception:
            await status_manager.mark_failed(task_name)
            traceback.print_exc(file=log_buffer)
            new_result = "fail"
        finally:
            await status_manager.update_message(task_name, "")
            log_buffer.close()

        results.append(FileGroup(files=files.files, result=new_result))

    sem = asyncio.Semaphore(max_workers)

    async def process_one_with_sem(index, files: FileGroup, task_name: str):
        async with sem:
            try:
                await process_one_fileset(index, files, task_name)
            except Exception:
                print("Unexpected error in task", task_name)
                traceback.print_exc()

    async with asyncio.TaskGroup() as tg:
        for i, file_set in enumerate(file_list):
            task_name = Path(file_set.files[0]).name
            if len(file_set.files) > 1:
                task_name = task_name + f" (+{len(file_set.files) - 1})"

            await status_manager.add_status(task_name)
            await status_manager.update_message(task_name, "Waiting...")
            tg.create_task(process_one_with_sem(i, file_set, task_name))

    print("Project run complete.")
    print("Failing files:")
    for file in results:
        if "fail" in file.result:
            for fn in file.files:
                print(fn)
    print("Passing files:")
    for file in results:
        if file.result == "pass":
            for fn in file.files:
                print(fn)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    results_file = f"manifest-{ts}.json"
    with open(results_file, "w") as f:
        result_manifest = manifest.model_copy(
            update={
                "files": results,
                "target_repo_ref": target_sha,
                "migrate_repo_ref": my_sha,
                "time": datetime.now(),
            }
        )
        f.write(
            result_manifest.model_dump_json(
                indent=2, exclude_defaults=True, exclude_none=True
            )
        )

    print(f"Results saved to {results_file}")
    return results


def init(
    path: str, pr: str = None, description: str = None, file_extension: str = "java"
):
    """Initialize a new AI migration project at the specified path.

    Args:
        path: Path where the project should be created
        pr: Optional PR number to use as a basis for the project
        description: Optional short description of the migration task
        file_extension: File extension for the migrated files
    """
    project_dir = Path(path).expanduser()

    if pr:
        # Use PR-based initialization if PR number is provided
        if not description:
            description = "Code migration task"

        import asyncio
        from .pr_utils import setup_project_from_pr

        asyncio.run(setup_project_from_pr(pr, path, description, file_extension))
        return

    # Traditional initialization
    if project_dir.exists() and any(project_dir.iterdir()):
        raise ValueError(f"Directory {project_dir} already exists and is not empty")
    project_dir.mkdir(exist_ok=True)
    for child in (
        "evals",
        "examples",
    ):
        (project_dir / child).mkdir(exist_ok=True)
        print(f"Created {project_dir / child}")

    system_prompt = project_dir / SYSTEM_PROMPT_FILE
    system_prompt.write_text(SYSTEM_MESSAGE)
    print("Created default system prompt at", system_prompt)

    verify_script = project_dir / VERIFY_SCRIPT_FILE
    verify_script.touch()
    print("Created empty verify script at", verify_script)

    print("To make this your default project,")
    print(f"    export AI_MIGRATE_PROJECT_DIR={project_dir.resolve()}")


def verify(project_dir: str, files: Iterable[str], manifest_file: str | None):
    if manifest_file:
        manifest = Manifest.model_validate_json(Path(manifest_file).read_text())
    else:
        manifest = Manifest()
    verify_cmd = manifest.verify_cmd.format(project_dir=project_dir, py=sys.executable)
    subprocess.run([*verify_cmd.split(), *files], check=True)


def pre_verify(project_dir: str, file: str, manifest_file: str | None):
    if manifest_file:
        manifest = Manifest.model_validate_json(Path(manifest_file).read_text())
    else:
        manifest = Manifest()
    verify_cmd = manifest.pre_verify_cmd.format(
        project_dir=project_dir, py=sys.executable
    )
    subprocess.run([*verify_cmd.split(), file], check=True)


def status():
    branches = get_branches()
    passing = []
    failing = []
    failed_to_start = []

    for ref, branch, status, msg in branches:
        if status == "pass":
            passing.append((ref, branch, msg))
        elif "fail" in status:
            failing.append((ref, branch, msg))
        else:
            failed_to_start.append((ref, branch, msg))

    def branch_to_filename(branch: str):
        filename = branch.removeprefix("ai-migrator/")
        parts = filename.split("__")
        if len(parts) > 3:
            parts = parts[:1] + ["..."] + parts[-2:]
        return "/".join(parts)

    def extract_attempts(msg: str) -> int | None:
        match = re.search(r"Migration attempt (\d+) status=", msg)
        if match:
            return match.group(1)

    def print_list(lst, status):
        if lst:
            print(f"{len(lst)} files {status}:")
            print(
                "\n".join(
                    f"{branch_to_filename(b)} ({extract_attempts(msg) or 'no'} attempts): {ref}"
                    for ref, b, msg in lst
                )
            )

    if not failing and not failed_to_start:
        print("All files passing! Ready to merge.")
    else:
        print_list(passing, "passing")
        print_list(failing, "failing")
        print_list(failed_to_start, "failed to start")


def checkout_failed(file, examples_dir="examples") -> None:
    branches = get_branches()
    matching = []
    for _sha, branch, _status, _msg in branches:
        if file in branch:
            matching.append(branch)
    if not matching:
        raise ValueError(f"No failed branches found for {file}")
    if len(matching) > 1:
        raise ValueError(f"Multiple failed branches found for {file}: {matching}")
    (failed_branch,) = matching
    subprocess.run(
        ["git", "checkout", "-b", f"repair-{failed_branch}", failed_branch], check=True
    )
    print("Checked out", failed_branch)
    print("Use `git log` to see what the migrator tried.")
