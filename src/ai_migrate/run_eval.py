import os
import shutil
import subprocess
import sys
import tempfile
import time
import logging
import argparse
from pathlib import Path

from ai_migrate.git_identity import environment_variables
from ai_migrate.manifest import Manifest

SCRIPT_DIR = Path(__file__).parent.parent.absolute()
AI_MIGRATE_PROJECT_DIR = SCRIPT_DIR.parent
EVALS_DIR = SCRIPT_DIR / "source"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ai_migrate.run_eval")


class Workspace:
    temp_dir: Path

    def __init__(self, verbose=False):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.working_dir = self.temp_dir
        self.verbose = verbose
        logger.debug(f"Created workspace at {self.temp_dir}")

    def sh(self, command, pipe_out=False, env=None):
        if env is None:
            env = {}

        logger.log(
            logging.INFO if self.verbose else logging.DEBUG,
            f"Running command: {command} in {self.working_dir}",
        )
        stderr_redirect = stdout_redirect = (
            None if pipe_out or self.verbose else subprocess.PIPE
        )

        try:
            result = subprocess.run(
                command.split(),
                check=True,
                cwd=self.working_dir,
                stdout=stdout_redirect,
                stderr=stderr_redirect,
                env={**os.environ, **env},
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed with return code {e.returncode}")
            logger.error("stdout:")
            logger.error(e.stdout)
            logger.error("stderr:")
            logger.error(e.stderr)
            raise

        logger.debug(f"Command completed with return code: {result.returncode}")
        return result

    def pushd(self, directory):
        logger.debug(
            f"Changing directory from {self.working_dir} to {self.working_dir / directory}"
        )
        self.working_dir = self.working_dir / directory

    def popd(self):
        if self.working_dir == self.temp_dir:
            raise ValueError("Cannot popd past the initial directory")
        old_dir = self.working_dir
        self.working_dir = self.working_dir.parent
        logger.debug(f"Changing directory back from {old_dir} to {self.working_dir}")

    def cleanup(self):
        logger.debug(f"Cleaning up workspace at {self.temp_dir}")
        shutil.rmtree(self.temp_dir)
        print("done cleaning up")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            logger.error(f"Exception in workspace: {exc_type.__name__}: {exc_val}")
        self.cleanup()


def run_project_eval(project, verbose=False):
    migrate_cmd = f"uv run --project {AI_MIGRATE_PROJECT_DIR} ai-migrate"
    with Workspace(verbose=verbose) as ws:
        logger.info(f"Running project eval for '{project}' in workspace {ws.temp_dir}")
        if verbose:
            logger.info("Verbose mode enabled - showing detailed output")

        start_time = time.time()
        project_dir = ws.temp_dir / "migrate-project"

        logger.info(
            f"Copying project files from {AI_MIGRATE_PROJECT_DIR / 'projects' / project} to {project_dir}"
        )
        shutil.copytree(AI_MIGRATE_PROJECT_DIR / "projects" / project, project_dir)

        eval_count = 0
        pass_count = 0
        fail_count = 0

        for directory in (project_dir / "evals").iterdir():
            eval_count += 1
            manifest_file = directory / "manifest.json"
            logger.info(f"Processing eval: {project}/{directory.name}")
            logger.info(f"Reading manifest file: {manifest_file}")

            manifest = Manifest.model_validate_json(manifest_file.read_text())
            logger.info(f"Manifest loaded with {len(manifest.files)} file entries")

            if manifest.eval_target_repo_remote and manifest.eval_target_repo_ref:
                logger.info(
                    f"Cloning target repo: {manifest.eval_target_repo_remote} @ {manifest.eval_target_repo_ref}"
                )
                ws.sh(f"git clone --depth=1 {manifest.eval_target_repo_remote} repo")
                ws.pushd("repo")
                ws.sh(f"git fetch --depth 1 origin {manifest.eval_target_repo_ref}")
                ws.sh(f"git checkout {manifest.eval_target_repo_ref}")
            else:
                logger.info(f"Using local source files from: {directory / 'source'}")
                shutil.copytree(directory / "source", ws.working_dir / "repo")
                ws.pushd("repo")
                ws.sh("git init")
                ws.sh("git add .")
                ws.sh("git commit -m initialcommit", env=environment_variables())

            try:
                logger.info(f"Running migration with manifest: {manifest_file}")
                command = [
                    migrate_cmd,
                    "migrate",
                    "--manifest-file",
                    str(manifest_file),
                    "--local-worktrees",
                    "--project-dir",
                    str(project_dir),
                ]
                if (fakes_directory := directory / "llm-fakes").exists():
                    command.extend(["--llm-fakes", str(fakes_directory)])
                ws.sh(
                    " ".join(command),
                    env={"AI_MIGRATE_PROJECT_DIR": project_dir},
                    pipe_out=True,
                )
                result = "PASSED"
                pass_count += 1
                logger.info(f"✅ Migration successful for {project}/{directory.name}")
            except subprocess.CalledProcessError:
                result = "FAILED"
                fail_count += 1
                logger.error(
                    f"❌ Error running migration for {project}/{directory.name}"
                )

                # Always show logs for failed migrations, regardless of verbose mode
                log_files = list((ws.working_dir / "ai-migrator-logs").glob("**/*.log"))
                logger.error(f"Found {len(log_files)} log files:")

                for log_file in log_files:
                    logger.error(f"Contents of {log_file}:")
                    log_content = log_file.read_text()
                    for line in log_content.splitlines():
                        logger.error(f"  | {line}")
                    logger.error("")

            print(f"{project}/{directory.name}", result)

            # Return to the parent directory for the next eval
            ws.popd()

        elapsed_time = time.time() - start_time
        logger.info(f"Completed {eval_count} evals in {elapsed_time:.2f}s")
        logger.info(f"Results: {pass_count} passed, {fail_count} failed")
        print(f"Done in {elapsed_time:.2f}s")

        return {
            "project": project,
            "total": eval_count,
            "passed": pass_count,
            "failed": fail_count,
            "time": elapsed_time,
        }


def main():
    parser = argparse.ArgumentParser(
        description="Run evaluations for AI migration projects"
    )
    parser.add_argument(
        "projects",
        nargs="*",
        help="Project names to evaluate. If none provided, all projects will be evaluated.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set the logging level",
    )
    parser.add_argument("--log-file", help="Log to a file in addition to console")

    args = parser.parse_args()

    # Configure logging based on arguments
    log_level = getattr(logging, args.log_level)
    logger.setLevel(log_level)

    # Add file handler if log file is specified
    if args.log_file:
        file_handler = logging.FileHandler(args.log_file)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(file_handler)
        logger.info(f"Logging to file: {args.log_file}")

    projects = args.projects

    if not projects:
        logger.info("No projects specified, discovering available projects...")
        projects_dir = Path(AI_MIGRATE_PROJECT_DIR / "projects")
        projects = []

        for directory in projects_dir.iterdir():
            if directory.is_dir() and (directory / "evals").is_dir():
                projects.append(directory.name)
                logger.info(f"Found project: {directory.name}")

    logger.info(
        f"Running evaluations for {len(projects)} projects: {', '.join(projects)}"
    )

    total_results = {
        "total_projects": len(projects),
        "total_evals": 0,
        "passed_evals": 0,
        "failed_evals": 0,
        "projects": [],
    }

    for project in projects:
        logger.info(f"Starting evaluation for project '{project}'")
        print(f"Running eval for project '{project}'")

        result = run_project_eval(project, verbose=args.verbose)
        total_results["total_evals"] += result["total"]
        total_results["passed_evals"] += result["passed"]
        total_results["failed_evals"] += result["failed"]
        total_results["projects"].append(result)

    # Print summary
    logger.info("=" * 50)
    logger.info("EVALUATION SUMMARY")
    logger.info("=" * 50)
    logger.info(f"Total projects evaluated: {total_results['total_projects']}")
    logger.info(f"Total evals run: {total_results['total_evals']}")
    logger.info(f"Passed evals: {total_results['passed_evals']}")
    logger.info(f"Failed evals: {total_results['failed_evals']}")

    if total_results["failed_evals"] > 0:
        logger.warning("Some evaluations failed. Check the logs for details.")
        return 1
    else:
        logger.info("All evaluations passed successfully!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
