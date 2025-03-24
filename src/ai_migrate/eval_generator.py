import os
import time
import json
import logging
import asyncio
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from .manifest import Manifest, FileEntry

logger = logging.getLogger("ai_migrate.eval_generator")
GITHUB_DOMAIN = "https://github.com/"


def generate_eval_from_migration(
    project_template,
    source_files,
    transformed_files,
    manifest: Manifest,
    eval_name=None,
):
    """
    Generate a new evaluation test case from a successful migration.

    Args:
        project_template: Path to the project template directory
        source_files: Dict mapping filenames to original content
        transformed_files: Dict mapping filenames to transformed content
        manifest: The manifest used for the migration (must be a Manifest object)
        eval_name: Optional name for the evaluation, defaults to timestamp-based name

    Returns:
        Path to the created evaluation directory
    """
    if eval_name is None:
        eval_name = f"auto_generated_{int(time.time())}"

    project_dir = Path(project_template)
    eval_dir = project_dir / "evals" / eval_name

    os.makedirs(eval_dir / "source", exist_ok=True)

    for filename, content in source_files.items():
        rel_path = Path(filename)
        file_path = eval_dir / "source" / rel_path.name
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w") as f:
            f.write(content)

    with open(eval_dir / "manifest.json", "w") as f:
        f.write(manifest.model_dump_json(indent=2))

    logger.info(f"Generated new evaluation: {eval_dir}")
    return eval_dir


class RepoInfo(BaseModel):
    """Pydantic model for GitHub repository information extracted from URLs."""

    owner: Optional[str] = None
    name: Optional[str] = None
    pr_number: Optional[str] = None

    @property
    def full_repo(self) -> Optional[str]:
        """Return the full repository name as owner/name if both are available."""
        if self.owner and self.name:
            return f"{self.owner}/{self.name}"
        return None


def extract_repo_info_from_url(url: str) -> RepoInfo:
    """Extract repository owner and name from various URL formats.

    Args:
        url: A GitHub URL or repo reference (e.g., 'https://github.com/owner/repo/pull/123' or 'owner/repo#123')

    Returns:
        RepoInfo: A Pydantic model containing extracted information
    """
    info = RepoInfo()

    if "#" in url:
        info.pr_number = url.split("#")[-1]
    elif "/pull/" in url:
        info.pr_number = url.split("/pull/")[-1]

    if info.pr_number and not info.pr_number.isdigit():
        logger.warning(
            f"PR number '{info.pr_number}' contains non-numeric characters. Using as is."
        )

    if "/" in url:
        parts = url.split("/")
        if len(parts) >= 5 and parts[2] == "github.com":
            info.owner = parts[3]
            info.name = parts[4].split("#")[0].split("/")[0]
        elif len(parts) >= 2:
            info.owner = parts[0]
            info.name = parts[1].split("#")[0]

    return info


async def generate_eval_from_pr(pr_url: str, project_template: str) -> Path:
    """Generate evaluation files from a PR.

    Args:
        pr_url: The PR URL or reference (e.g., 'https://github.com/owner/repo/pull/123' or 'owner/repo#123')
        project_template: Path to the project template directory

    Returns:
        Path to the created evaluation directory
    """
    project_dir = Path(project_template).expanduser()
    evals_dir = project_dir / "evals"
    evals_dir.mkdir(exist_ok=True)

    original_pr_url = pr_url

    repo_info = extract_repo_info_from_url(original_pr_url)

    pr_number = repo_info.pr_number or str(int(time.time()))

    try:
        logger.info(f"Fetching PR details for: {original_pr_url}")
        result = await asyncio.create_subprocess_exec(
            "gh",
            "pr",
            "view",
            original_pr_url,
            "--json",
            "title,headRepository,baseRefName,headRefName,baseRefOid,headRefOid,files",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = await result.communicate()

        if result.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            logger.error(f"Failed to get PR details: {error_msg}")

            if "not authenticated" in error_msg or "Unauthorized" in error_msg:
                raise ValueError(
                    f"GitHub authentication error. Please run 'gh auth login' to authenticate with GitHub.\n"
                    f"Error details: {error_msg}"
                )

            if (
                "Could not resolve to a Repository" in error_msg
                or "Could not resolve to a PullRequest" in error_msg
            ):
                msg = "Could not access the repository"
                if repo_info.full_repo:
                    msg += f" {repo_info.full_repo}"
                elif repo_info.name:
                    msg += f" {repo_info.name}"
                msg += (
                    ". Make sure you have access to the repository and the PR exists.\n"
                )
                msg += f"Error details: {error_msg}"
                raise ValueError(msg)

            raise ValueError(f"Failed to get PR details: {error_msg}")

        pr_details = json.loads(stdout.decode())
    except json.JSONDecodeError:
        logger.error("Invalid JSON response from GitHub CLI")
        raise ValueError(
            "Invalid response from GitHub CLI. Please check your GitHub CLI installation and authentication."
        )

    repo_name = f"pr-{pr_number}"
    if "headRepository" in pr_details and "name" in pr_details["headRepository"]:
        repo_name = pr_details["headRepository"]["name"]

    eval_name = f"{repo_name}-{int(time.time())}"
    eval_dir = evals_dir / eval_name
    eval_dir.mkdir(exist_ok=True)

    base_ref = pr_details.get("baseRefOid", "")

    changed_files = []
    if "files" in pr_details and isinstance(pr_details["files"], list):
        changed_files = [
            file_info["path"]
            for file_info in pr_details["files"]
            if isinstance(file_info, dict) and "path" in file_info
        ]

    repo_url = ""
    if "headRepository" in pr_details and "url" in pr_details["headRepository"]:
        repo_url = pr_details["headRepository"]["url"]

        if repo_url.startswith(GITHUB_DOMAIN):
            repo_url = f"github@github.com:{repo_url[len(GITHUB_DOMAIN) :]}.git"

    manifest = Manifest(
        eval_target_repo_remote=repo_url,
        eval_target_repo_ref=base_ref,
        files=[
            FileEntry(filename=file_path, result="?")
            for file_path in changed_files[:10]
        ],
    )

    manifest_file = eval_dir / "manifest.json"
    with open(manifest_file, "w") as f:
        f.write(manifest.model_dump_json(indent=2))

    source_dir = eval_dir / "source"
    source_dir.mkdir(exist_ok=True)

    if base_ref and changed_files:
        with tempfile.TemporaryDirectory() as temp_dir:
            clone_url = (
                repo_url
                if repo_url
                else f"https://github.com/{pr_details['headRepository']['owner']['login']}/{pr_details['headRepository']['name']}.git"
            )

            clone_result = await asyncio.create_subprocess_exec(
                "git",
                "clone",
                "--depth=1",
                clone_url,
                temp_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            clone_stdout, clone_stderr = await clone_result.communicate()

            if clone_result.returncode != 0:
                error_msg = clone_stderr.decode() if clone_stderr else "Unknown error"
                logger.warning(f"Failed to clone repository: {error_msg}")

                raise subprocess.CalledProcessError(
                    clone_result.returncode,
                    ["git", "clone", "--depth=1", clone_url, temp_dir],
                    output=clone_stdout,
                    stderr=clone_stderr,
                )

            checkout_result = await asyncio.create_subprocess_exec(
                "git",
                "checkout",
                base_ref,
                cwd=temp_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            checkout_stdout, checkout_stderr = await checkout_result.communicate()

            if checkout_result.returncode != 0:
                error_msg = (
                    checkout_stderr.decode() if checkout_stderr else "Unknown error"
                )
                logger.warning(f"Failed to checkout base commit: {error_msg}")

                raise subprocess.CalledProcessError(
                    checkout_result.returncode,
                    ["git", "checkout", base_ref],
                    output=checkout_stdout,
                    stderr=checkout_stderr,
                )

            for file_path in changed_files:
                src_file = Path(temp_dir) / file_path
                if src_file.exists():
                    dst_file = source_dir / file_path
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copy2(src_file, dst_file)
                    except (IOError, OSError) as e:
                        logger.warning(f"Failed to copy file {file_path}: {e}")

    logger.info(f"Generated evaluation at {eval_dir}")
    return eval_dir
