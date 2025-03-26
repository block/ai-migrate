"""
Interactive CLI for AI Migrate using Click, Rich, and Prompt_toolkit.

Environment Variables:
- AI_MIGRATE_PROJECT_DIR: Path to the project directory
- AI_MIGRATE_PROJECT_NAME: Project name (required when not in interactive mode)
- AI_MIGRATE_PROJECT_PATH: Project path (required when not in interactive mode)
- AI_MIGRATE_OPTION: Option to select in non-interactive mode for radiolist choices
- AI_MIGRATE_YES_NO: Option to select in non-interactive mode for yes/no choices ('yes' or 'no')
"""

import os
import re
import sys
import json
import asyncio
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Callable, Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.markdown import Markdown
from prompt_toolkit import prompt
from prompt_toolkit.completion import PathCompleter

from ai_migrate.git import get_branches, get_worktrees
from ai_migrate.projects_root import get_project_dir
from .pr_utils import (
    setup_project_from_pr,
    get_pr_details,
    extract_example_patterns,
    save_examples,
    generate_system_prompt,
)
from .manifest import SYSTEM_PROMPT_FILE, Manifest
from .migrate import SYSTEM_MESSAGE
from .eval_generator import generate_eval_from_pr
from ai_migrate.llm_providers import DefaultClient
from .examples import setup as setup_examples, setup_from_pr

IS_INTERACTIVE = sys.stdin.isatty()

console = Console()


def print_header():
    """Print a stylized header for the CLI."""
    console.print(
        Panel.fit(
            "[bold blue]AI Migrate[/bold blue] - Code Migration Tool",
            border_style="blue",
        )
    )
    console.print()


def console_radiolist(title: str, text: str, values: list) -> str:
    """Console-based alternative to radiolist_dialog."""
    console.print(f"[bold blue]{title}[/bold blue]")
    console.print(text)
    console.print()

    for i, (value, description) in enumerate(values, 1):
        console.print(f"[bold cyan]{i}.[/bold cyan] {value} - {description}")

    console.print()

    if not IS_INTERACTIVE:
        option = os.environ.get("AI_MIGRATE_OPTION")
        if option:
            for value, _ in values:
                if value == option:
                    console.print(
                        f"[yellow]Not in interactive terminal. Using provided option: {option}[/yellow]"
                    )
                    return value

            console.print(
                f"[red]Error: Provided option '{option}' is not valid. Available options: {[v[0] for v in values]}[/red]"
            )
            return None
        else:
            console.print(
                "[red]Error: Not in interactive terminal and no option provided via AI_MIGRATE_OPTION environment variable.[/red]"
            )
            return None

    while True:
        choice = prompt(f"Enter your choice (1-{len(values)}, or 'q' to cancel): ")
        if choice.lower() == "q":
            return None

        try:
            index = int(choice) - 1
            if 0 <= index < len(values):
                return values[index][0]
            else:
                console.print("[yellow]Invalid choice. Please try again.[/yellow]")
        except ValueError:
            console.print("[yellow]Please enter a number or 'q' to cancel.[/yellow]")


def console_yes_no(title: str, text: str) -> bool:
    """Console-based alternative to yes_no_dialog."""
    console.print(f"[bold blue]{title}[/bold blue]")
    console.print(text)
    console.print()

    if not IS_INTERACTIVE:
        option = os.environ.get("AI_MIGRATE_YES_NO")
        if option:
            if option.lower() in ("y", "yes", "true"):
                console.print(
                    "[yellow]Not in interactive terminal. Using provided option: yes[/yellow]"
                )
                return True
            elif option.lower() in ("n", "no", "false"):
                console.print(
                    "[yellow]Not in interactive terminal. Using provided option: no[/yellow]"
                )
                return False
            else:
                console.print(
                    f"[red]Error: Provided option '{option}' is not valid. Use 'yes' or 'no'.[/red]"
                )
                return False
        else:
            console.print(
                "[red]Error: Not in interactive terminal and no option provided via AI_MIGRATE_YES_NO environment variable.[/red]"
            )
            return False

    while True:
        choice = prompt("Enter your choice (y/n): ").lower()
        if choice in ("y", "yes"):
            return True
        elif choice in ("n", "no"):
            return False
        else:
            console.print("[yellow]Please enter 'y' or 'n'.[/yellow]")


def run_with_progress(description: str, func: Callable, *args, **kwargs) -> Any:
    """Run a function with a progress indicator."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(f"[bold blue]{description}", total=None)

        try:
            result = func(*args, **kwargs)
            progress.update(task, completed=True)
            return result, None
        except Exception as e:
            progress.update(task, completed=True)
            return None, e


def run_async_with_progress(description: str, func: Callable, *args, **kwargs) -> Any:
    """Run an async function with a progress indicator."""

    async def wrapper():
        return await func(*args, **kwargs)

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(f"[bold blue]{description}", total=None)

        try:
            result = asyncio.run(wrapper())
            progress.update(task, completed=True)
            return result, None
        except Exception as e:
            progress.update(task, completed=True)
            return None, e


def show_success_message(message: str):
    """Show a success message."""
    console.print(f"[green]✓[/green] {message}")


def show_error_message(message: str, error=None):
    """Show an error message."""

    safe_message = message.replace("[", "\\[").replace("]", "\\]")
    console.print(f"[red]✗[/red] {safe_message}")
    if error:
        safe_error = str(error).replace("[", "\\[").replace("]", "\\]")
        console.print(f"[red]Error details:[/red] {safe_error}")


def show_warning_message(message: str):
    """Show a warning message."""
    console.print(f"[yellow]Warning:[/yellow] {message}")


def manage_examples(project_dir: Path):
    """Manage example files."""
    examples_dir = project_dir / "examples"
    if not examples_dir.exists():
        show_error_message(f"Examples directory {examples_dir} does not exist.")
        return

    action = console_radiolist(
        title="Examples Management",
        text="What would you like to do?",
        values=[
            ("list", "List existing examples"),
            ("add", "Add a new example"),
            ("from-pr", "Generate examples from a PR"),
            ("setup", "Setup examples from git history"),
        ],
    )

    if not action:
        return

    if action == "list":
        files = list(examples_dir.glob("*"))

        if not files:
            console.print("No examples found.")
            return

        table = Table(title="Example Files")
        table.add_column("Filename", style="cyan")
        table.add_column("Type", style="green")
        table.add_column("Size", justify="right", style="blue")

        for file in files:
            file_type = (
                "Old"
                if ".old." in file.name
                else "New"
                if ".new." in file.name
                else "Unknown"
            )
            table.add_row(file.name, file_type, f"{file.stat().st_size} bytes")

        console.print(table)

    elif action == "add":
        file_path = prompt(
            "Enter path to the file to add as example: ", completer=PathCompleter()
        )

        file_path = Path(file_path).absolute()
        if not file_path.exists():
            show_error_message(f"File {file_path} does not exist.")
            return

        example_type = console_radiolist(
            title="Example Type",
            text="Is this an old (before) or new (after) example?",
            values=[
                ("old", "Old (before migration)"),
                ("new", "New (after migration)"),
            ],
        )

        if not example_type:
            return

        base_name = prompt("Enter base name for the example: ", default=file_path.stem)

        target_path = examples_dir / f"{base_name}.{example_type}{file_path.suffix}"
        with open(file_path, "r") as src, open(target_path, "w") as dst:
            dst.write(src.read())

        show_success_message(f"Example added as {target_path.name}")

    elif action == "from-pr":
        pr_number = prompt("Enter PR link: ")
        file_extension = prompt(
            "Enter file extension for examples (default: java): ", default="java"
        )

        async def generate_examples():
            pr_details = await get_pr_details(pr_number)
            examples = await extract_example_patterns(pr_number, pr_details)

            if not examples:
                print(
                    "Warning: No example patterns were extracted. Creating a simple example..."
                )

                examples = [
                    (
                        "// Old version\npublic class Example {\n    // TODO: Add your code here\n}",
                        "// New version\npublic class Example {\n    // TODO: Migrated code here\n}",
                    )
                ]

            await save_examples(examples, examples_dir, file_extension)
            return len(examples)

        num_examples, error = run_async_with_progress(
            "Generating examples from PR...", generate_examples
        )

        if error:
            show_error_message("Error generating examples", error)
        elif num_examples > 0:
            show_success_message(
                f"Generated {num_examples} example pairs from PR #{pr_number}"
            )
        else:
            show_warning_message(f"No examples were generated from PR #{pr_number}")
            console.print("You may need to create examples manually.")

    elif action == "setup":
        ref = prompt("Enter git ref: ")
        pattern = prompt("Enter file pattern (optional): ", default="")

        result, error = run_with_progress(
            "Setting up examples from git history...",
            setup_examples,
            ref,
            str(examples_dir),
            pattern if pattern else None,
        )

        if error:
            show_error_message("Error setting up examples", error)
        else:
            show_success_message(f"Examples set up from git ref {ref}")


def manage_evals(project_dir: Path):
    """Manage evaluation test cases."""
    evals_dir = project_dir / "evals"
    if not evals_dir.exists():
        evals_dir.mkdir(exist_ok=True)
        show_success_message(f"Created evals directory at {evals_dir}")

    action = console_radiolist(
        title="Evaluations Management",
        text="What would you like to do?",
        values=[
            ("list", "List existing evaluations"),
            ("from-pr", "Generate evaluations from a PR"),
            ("from-migration", "Generate evaluation from a recent migration"),
        ],
    )

    if not action:
        return

    if action == "list":
        eval_dirs = [d for d in evals_dir.iterdir() if d.is_dir()]

        if not eval_dirs:
            console.print("No evaluations found.")
            return

        table = Table(title="Evaluations")
        table.add_column("Name", style="cyan")
        table.add_column("Files", style="green")
        table.add_column("Created", style="blue")

        for eval_dir in eval_dirs:
            source_dir = eval_dir / "source"
            files = list(source_dir.glob("*")) if source_dir.exists() else []
            created = datetime.fromtimestamp(eval_dir.stat().st_ctime).strftime(
                "%Y-%m-%d %H:%M"
            )
            table.add_row(eval_dir.name, str(len(files)), created)

        console.print(table)

    elif action == "from-pr":
        pr_number = prompt("Enter PR link: ")

        result, error = run_async_with_progress(
            "Generating evaluations from PR...",
            generate_eval_from_pr,
            pr_number,
            str(project_dir),
        )

        if error:
            show_error_message("Error generating evaluations", error)
            return error
        else:
            show_success_message(
                f"Generated evaluations from PR #{pr_number} at {result}"
            )

    elif action == "from-migration":
        console.print("This feature is not yet implemented.")


def manage_system_prompt(project_dir: Path):
    """View or edit the system prompt."""
    system_prompt_path = project_dir / SYSTEM_PROMPT_FILE

    if not system_prompt_path.exists():
        show_error_message(f"System prompt file {system_prompt_path} does not exist.")
        return

    action = console_radiolist(
        title="System Prompt",
        text="What would you like to do?",
        values=[
            ("view", "View the current system prompt"),
            ("edit", "Edit the system prompt"),
            ("generate", "Generate a new system prompt"),
        ],
    )

    if not action:
        return

    if action == "view":
        content = system_prompt_path.read_text()
        console.print(
            Panel(Markdown(content), title="System Prompt", border_style="blue")
        )

    elif action == "edit":
        content = system_prompt_path.read_text()

        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        editor = os.environ.get("EDITOR", "nano")
        subprocess.run([editor, tmp_path])

        with open(tmp_path, "r") as f:
            new_content = f.read()

        os.unlink(tmp_path)

        if new_content != content:
            system_prompt_path.write_text(new_content)
            show_success_message("System prompt updated.")
        else:
            console.print("System prompt not changed.")

    elif action == "generate":
        method = console_radiolist(
            title="Generation Method",
            text="How would you like to generate the system prompt?",
            values=[
                ("pr", "From a PR"),
                ("description", "From a description"),
            ],
        )

        if not method:
            return

        if method == "pr":
            pr_number = prompt("Enter PR link: ")
            description = prompt("Enter a brief description of the migration task: ")

            async def generate_prompt():
                pr_details = await get_pr_details(pr_number)
                return await generate_system_prompt(pr_details, description)

            system_prompt, error = run_async_with_progress(
                "Generating system prompt...", generate_prompt
            )

            if error:
                show_error_message("Error generating system prompt", error)
                return

        elif method == "description":
            description = prompt("Enter a detailed description of the migration task: ")

            async def generate_prompt():
                client = DefaultClient()
                system_prompt_for_generation = """You are an expert at creating system prompts for code migration tasks.
Create a clear, concise system prompt that will guide an AI to perform code migrations based on the description provided."""

                user_prompt = f"""
I need to create a system prompt for a code migration task. Here's the description:

{description}

Create a system prompt that clearly explains:
1. The migration goal
2. Key patterns to look for
3. How to transform the code
4. Any important constraints or considerations

The system prompt should be concise but comprehensive, focusing on the migration patterns.
"""

                return await client.generate_text(
                    system_prompt_for_generation, user_prompt
                )

            system_prompt, error = run_async_with_progress(
                "Generating system prompt...", generate_prompt
            )

            if error:
                show_error_message("Error generating system prompt", error)
                return

        console.print(
            Panel(
                Markdown(system_prompt),
                title="Generated System Prompt",
                border_style="blue",
            )
        )

        if console_yes_no(
            title="Save System Prompt",
            text="Do you want to save this system prompt?",
        ):
            system_prompt_path.write_text(system_prompt)
            show_success_message(f"System prompt saved to {system_prompt_path}")


@click.group()
def cli():
    """AI Migrate - Code Migration Tool."""
    print_header()


@cli.command()
@click.option(
    "--interactive/--no-interactive", default=True, help="Run in interactive mode"
)
def init(interactive):
    """Initialize a new migration project."""
    if not interactive:
        click.echo("Please use the interactive mode for better experience.")
        return

    project_name = prompt("Enter project name: ")
    default_path = Path.cwd()
    if not default_path.name == "projects":
        default_path = default_path / "projects"
    default_path = default_path / project_name
    project_path = Path(
        prompt(
            "Enter project directory path: ",
            completer=PathCompleter(),
            default=str(default_path),
        ).strip()
    )

    if project_path.exists() and any(project_path.iterdir()):
        if not console_yes_no(
            title="Directory not empty",
            text=f"The directory {project_path} already exists and is not empty. Continue anyway?",
        ):
            return

    use_pr = console_yes_no(
        title="PR-Based Initialization",
        text="Do you want to initialize the project based on a GitHub PR?",
    )

    generate_evals = False

    if use_pr:
        pr_number = prompt("Enter PR link: ")
        description = prompt("Enter a brief description of the migration task: ")
        file_extension = prompt(
            "Enter file extension for examples (default: java): ", default="java"
        )

        generate_evals = console_yes_no(
            title="Generate Evaluations",
            text="Do you want to generate evaluation files from this PR?",
        )

        result, error = run_async_with_progress(
            "Initializing project from PR...",
            setup_project_from_pr,
            pr_number,
            str(project_path),
            description,
            file_extension,
        )

        if error:
            show_error_message(f"Error during project initialization: {error}")
            show_warning_message(
                "Project was created with minimal files. Some manual editing may be required."
            )
        else:
            show_success_message(f"Project initialized successfully at {project_path}")

            if generate_evals and pr_number:
                result, error = run_async_with_progress(
                    "Generating evaluation files from PR...",
                    generate_eval_from_pr,
                    pr_number,
                    str(project_path),
                )

                if error:
                    show_error_message(f"Error generating evaluation files: {error}")
                    show_warning_message(
                        "You may need to create evaluation files manually."
                    )
                else:
                    show_success_message("Evaluation files generated successfully")
    else:
        project_path.mkdir(parents=True, exist_ok=True)
        examples_dir = project_path / "examples"
        examples_dir.mkdir(exist_ok=True)
        evals_dir = project_path / "evals"
        evals_dir.mkdir(exist_ok=True)

        system_prompt = project_path / SYSTEM_PROMPT_FILE
        system_prompt.write_text(SYSTEM_MESSAGE)

        show_success_message(f"Project initialized successfully at {project_path}")

    console.print("\nNext steps:")
    console.print("1. Review the generated system prompt")
    console.print("2. Review the generated examples")
    console.print(
        f"\nTo set this as your default project: [bold]export AI_MIGRATE_PROJECT_DIR={project_path}[/bold]"
    )


def project_dir_option(f):
    def project_dir_validate(ctx, param, project_dir):
        if "project_dir" in ctx.params:
            return ctx.params["project_dir"]

        if "--project" in param.opts:
            project_dir = get_project_dir(project_dir)
            return project_dir

        if not project_dir:
            project_dir = os.environ.get("AI_MIGRATE_PROJECT_DIR")

        if not project_dir and Path(".ai-migrate").exists():
            try:
                project_dir = json.loads(Path(".ai-migrate").read_text())["project_dir"]
            except (json.JSONDecodeError, KeyError):
                pass

        if not project_dir:
            console.print("[yellow]No project directory specified.[/yellow]")
            console.print(
                "Please specify a project directory using --project-dir or set AI_MIGRATE_PROJECT_DIR environment variable."
            )
            raise click.MissingParameter("project_dir")

        project_dir = Path(project_dir).expanduser().absolute()

        if not project_dir.exists():
            raise click.BadParameter(f"Project directory {project_dir} does not exist.")

        return project_dir

    return click.option(
        "--project",
        "project_dir",
        help="A pre-configured project",
        callback=project_dir_validate,
    )(
        click.option(
            "--project-dir",
            "project_dir",
            help="Path to the project directory",
            callback=project_dir_validate,
        )(f)
    )


@cli.command()
@click.argument("file_paths", nargs=-1)
@project_dir_option
@click.option(
    "--manage",
    type=click.Choice(["examples", "system-prompt", "evals"]),
    help="Manage examples, system prompt, or evaluations",
)
@click.option("--manifest-file", help="Path to the manifest file")
@click.option(
    "--rerun-passed/--only-failed",
    default=False,
    help="Re-run migrations that have already passed",
)
@click.option(
    "--max-workers", default=8, type=int, help="Maximum number of parallel workers"
)
@click.option(
    "--local-worktrees/--no-local-worktrees",
    default=False,
    help="Create worktrees alongside the git repo",
)
@click.option(
    "--llm-fakes",
    default=None,
    type=str,
    help="Use fake LLM responses for testing",
)
@click.option(
    "--dont-create-evals",
    is_flag=True,
    help="Don't automatically create evaluations after successful migrations",
)
def migrate(
    file_paths,
    project_dir,
    manage,
    manifest_file,
    rerun_passed,
    max_workers,
    local_worktrees,
    llm_fakes,
    dont_create_evals,
):
    """Migrate one or more files or manage project resources.

    If --manage is specified, you can manage examples, system prompt, or evaluations instead of migrating files.
    """
    console.print(f"Using project: [bold cyan]{project_dir}[/bold cyan]")

    if manage:
        if manage == "examples":
            manage_examples(project_dir)
            return
        elif manage == "system-prompt":
            manage_system_prompt(project_dir)
            return
        elif manage == "evals":
            manage_evals(project_dir)
            return

    from .projects import run as projects_run

    if not file_paths and not manifest_file:
        if (make_manifest_script := (Path(project_dir) / "make_manifest.py")).exists():
            console.print("Found make_manifest.py in project directory. Running...")
            try:
                manifest_json = subprocess.run(
                    [sys.executable, make_manifest_script],
                    capture_output=True,
                    check=True,
                ).stdout.decode()
            except subprocess.CalledProcessError as e:
                show_error_message("Error running make_manifest.py", e.stderr.decode())
                raise
            dt = datetime.now().strftime("%Y%m%d-%H%M%S")
            manifest_file = f"manifest-{dt}.json"
            with open(manifest_file, "w") as f:
                f.write(manifest_json)
            print("Manifest file created:", manifest_file)
        elif not IS_INTERACTIVE:
            console.print(
                "[yellow]No files specified and not in interactive terminal. Please specify files using command line arguments.[/yellow]"
            )
            return
        else:
            file_path = prompt(
                "Enter file path to migrate: ", completer=PathCompleter()
            )
            file_paths = [file_path]

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    logs_dir = Path("ai-migrator-logs") / run_id
    result = asyncio.run(
        projects_run(
            str(project_dir),
            logs_dir,
            manifest_file,
            file_paths,
            not rerun_passed,
            max_workers,
            local_worktrees,
            resume=True,
            llm_fakes=llm_fakes,
            dont_create_evals=dont_create_evals,
        )
    )

    has_failures = any("fail" in fg.result for fg in result)
    has_pre_verify_failures = any(fg.result == "pre-verify-fail" for fg in result)
    if has_failures:
        show_error_message("Migration failed: some files did not pass verification")
        console.print(f"Logs are available at {logs_dir}")
        console.print(f"View them with `ai-migrate logs {run_id}`")
        if has_pre_verify_failures:
            console.print("Some files failed pre-verification.")
            logs()

        sys.exit(1)


@cli.command()
@click.option("--project-dir", help="Path to the project directory")
@click.option("--manifest")
def status(
    project_dir,
    manifest,
):
    """Show the status of migration projects."""

    from .projects import status as projects_status

    result, error = run_with_progress("Getting migration status...", projects_status)

    if error:
        show_error_message("Failed to get migration status", error)


@cli.command()
@click.argument("file_path")
@project_dir_option
def checkout(file_path, project_dir):
    """Check out the branch for a file to try manual fixes on a failed migration attempt."""

    from .projects import checkout_failed

    result, error = run_with_progress(
        f"Checking out branch for {file_path}...", checkout_failed, file_path
    )

    if error:
        show_error_message(f"Failed to checkout branch for {file_path}", error)
    else:
        show_success_message(f"Successfully checked out branch for {file_path}")


@cli.command()
@click.argument("manifest")
def merge_branches(manifest):
    """Merge the changes from the migrator branches."""
    from .merge_migrator_changes import merge

    result, error = run_with_progress(
        "Merging changes from migrator branches...", merge, manifest
    )

    if error:
        show_error_message("Failed to merge changes", error)
    else:
        show_success_message("Successfully merged changes from migrator branches")


@cli.command
@click.argument("files", nargs=-1)
@project_dir_option
def verify(project_dir, files):
    """Run the verification step over a file"""
    from .projects import verify

    verify(project_dir, files, manifest_file=None)


@cli.command()
@click.argument("run_id", default="latest")
def logs(run_id):
    """Show the logs for a given run."""
    if run_id == "latest":
        candidates = sorted(
            [
                logs_dir.name
                for logs_dir in Path("ai-migrator-logs").iterdir()
                if logs_dir.is_dir() and re.match(r"^\d{8}-\d{6}$", logs_dir.name)
            ]
        )
        if not candidates:
            console.print("[red]No logs found.[/red]")
            return
        run_id = candidates[-1]
        print(f"Using latest run: {run_id}")

    logs_dir = Path("ai-migrator-logs") / run_id

    for log_file in logs_dir.glob("*.log"):
        print(f"{log_file}:")
        with open(log_file) as f:
            print(f.read())
        print()


@cli.command()
@project_dir_option
@click.argument("pr_num")
def add_examples_from_pr(pr_num, project_dir):
    setup_from_pr(pr_num, Path(project_dir) / "examples")


@cli.command()
@click.argument("manifest")
@click.option("--force", default=False, is_flag=True)
def cleanup_git_branches(manifest, force):
    """Clean up git worktrees and branches created by the migrator."""
    branches = {
        branch
        for _, branch, *_ in get_branches(
            Manifest.model_validate_json(Path(manifest).read_text())
        )
    }

    subprocess.run(["git", "worktree", "prune"], check=True)
    for worktree, branch, prunable in get_worktrees():
        if branch in branches:
            if prunable or force:
                subprocess.run(["git", "worktree", "remove", "--force", worktree])
            else:
                console.print(
                    f"[yellow]Worktree {worktree} for branch {branch} is not prunable. Use --force to remove it.[/yellow]"
                )
                branches.remove(branch)

    for branch in branches:
        assert branch.startswith("ai-migrator/")
        subprocess.run(["git", "branch", "-D" if force else "-d", branch])


@cli.command()
@project_dir_option
@click.argument("script")
def script(script, project_dir):
    """Run a script from the project directory"""
    script_path = Path(project_dir) / script
    if (py_script := script_path.with_suffix(".py")).exists():
        command = [sys.executable, py_script]
    elif (sh_script := script_path.with_suffix(".sh")).exists():
        command = [sh_script]
    else:
        show_error_message(f"Script {script} not found in project directory.")
        return

    console.print(f"Running script: [bold cyan]{script_path}[/bold cyan]")
    subprocess.run(command, check=True)


@cli.command()
@project_dir_option
def current_project(project_dir):
    """Show the project directory."""
    console.print(f"Project directory: [bold cyan]{project_dir}[/bold cyan]")


def main():
    """Entry point for the interactive CLI."""
    try:
        cli()
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user.[/yellow]")
        sys.exit(1)
    except Exception as e:
        error_msg = str(e).replace("[", "\\[").replace("]", "\\]")
        console.print(f"\n[red]Error:[/red] {error_msg}")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
