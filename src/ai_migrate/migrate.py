import asyncio
import contextvars
import os
import shutil
import sys
import tempfile
import traceback
from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Any, Iterable, Optional

from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import Tool

from ai_migrate.llm_providers import DefaultClient
from .context import MigrationContext, ToolCallContext
from .fake_llm_client import FakeLLMClient
from .git_identity import environment_variables
from .manifest import FileGroup, FileEntry, GooseConfig, Manifest
from .eval_generator import generate_eval_from_migration


ROLE_ASSISTANT = "assistant"
ROLE_USER = "user"

LOG_STREAM = contextvars.ContextVar("LOG_STREAM", default=sys.stdout)


def log(*args, **kwargs):
    print(*args, **kwargs, file=LOG_STREAM.get(), flush=True)


@dataclass
class FileContent:
    name: str
    content: str


@dataclass
class MigrationExample:
    name: Optional[str]
    old_files: list[FileContent]
    new_files: list[FileContent]


def read_file_pairs_from(examples_dir: str | Path) -> Iterable[MigrationExample]:
    """
    Read pairs of files from the examples directory, matching .old and .new directories.
    Returns an Iterable of MigrationExample containing all files in each directory pair.

    Sample dir:
    examples/
      example1.old/
        src/
          file1.py
          file2.py
      example1.new/
        src/
          file1.py
          file2.py
      single.old.py
      single.new.py

    Args:
        examples_dir: Directory containing example migration pairs

    Returns:
        Iterable[MigrationExample]: Iterator of migration examples
    """
    examples_dir = Path(examples_dir)

    def get_files_recursively(directory: Path) -> list[FileContent]:
        """Recursively get all files in a directory, maintaining relative paths."""
        files = []
        for item in directory.rglob("*"):
            if item.is_file():
                relative_path = item.relative_to(directory)
                files.append(
                    FileContent(name=str(relative_path), content=item.read_text())
                )
        return files

    old_dirs = [
        d for d in examples_dir.iterdir() if d.is_dir() and d.name.endswith(".old")
    ]

    for old_dir in old_dirs:
        base_name = old_dir.name.removesuffix(".old")
        new_dir = old_dir.parent / f"{base_name}.new"

        if new_dir.exists() and new_dir.is_dir():
            old_files = get_files_recursively(old_dir)
            new_files = get_files_recursively(new_dir)

            yield MigrationExample(
                name=base_name, old_files=old_files, new_files=new_files
            )

    for file in examples_dir.iterdir():
        if file.is_file() and ".old." in file.name:
            base, ext = file.name.split(".old.", 1)
            new_file = file.parent / f"{base}.new.{ext}"

            if new_file.exists():
                old_content = FileContent(
                    name=f"{base}.{ext}", content=file.read_text()
                )
                new_content = FileContent(
                    name=f"{base}.{ext}", content=new_file.read_text()
                )

                yield MigrationExample(
                    name=base, old_files=[old_content], new_files=[new_content]
                )


NBSP_REPLACEMENT_TOKEN = "<LLM-NBSP>"


def escape_nbsp(text: str) -> str:
    """LLMs tokenize these as regular spaces. In source code they need to be preserved."""
    return text.replace("\u00a0", "<LLM-NBSP>")


def un_escape_nbsp(text: str) -> str:
    """LLMs tokenize these as regular spaces. In source code they need to be preserved."""
    return text.replace("<LLM-NBSP>", "\u00a0")


LANGUAGE_EXTENSIONS = {
    "bash": [".sh", ".bash"],
    "python": [".py", ".pyx", ".pyi"],
    "ruby": [".rb", ".rake"],
    "javascript": [".js", ".jsx", ".mjs"],
    "css": [".css", ".cssx"],
    "html": [".html", ".htm", ".htmx"],
    "typescript": [".ts", ".tsx"],
    "java": [".java"],
    "go": [".go"],
    "rust": [".rs"],
    "php": [".php"],
    "swift": [".swift"],
    "kotlin": [".kt", ".kts"],
    "gradle": [".grad"],
    "terraform": [".tf"],
}


def detect_language(filename: str) -> str:
    extension = Path(filename).suffix
    for language, extensions in LANGUAGE_EXTENSIONS.items():
        for e in extensions:
            if e == extension:
                return language
    return ""


def wrap_in_code_block(text: str, filename: str | None) -> str:
    language = detect_language(filename)
    code_block = f"```{language}\n{text.strip()}\n```"
    if filename:
        code_block = f"### `{filename}`\n{code_block}"
    return code_block


def migrate_prompt(example: MigrationExample) -> list[dict]:
    """
    Create a prompt for migrating code based on a MigrationExample.

    Args:
        example: MigrationExample containing old and new files

    Returns:
        List of messages for the LLM conversation
    """
    old_file_contents = "\n\n".join(
        wrap_in_code_block(fc.content, fc.name) for fc in example.old_files
    )
    user_message = {
        "role": ROLE_USER,
        "content": f"Migrate this code to the new format:\n\n{escape_nbsp(old_file_contents)}. "
        "Return the full content for all files mentioned, don't leave anything out. "
        "You can rename a file if necessary.",
    }

    if example.new_files:
        new_file_blocks = [
            wrap_in_code_block(fc.content, fc.name) for fc in example.new_files
        ]
        new_file_contents = "\n\n".join(new_file_blocks)
        assistant_message = {
            "role": ROLE_ASSISTANT,
            "content": f"Here's the migrated code:\n{escape_nbsp(new_file_contents)}",
        }
        return [user_message, assistant_message]
    return [user_message]


async def handle_tool_calls(
    tools: list[Tool], tool_calls: list[dict[str, Any]], context: MigrationContext
) -> list[dict[str, str]]:
    tool_results = []
    tools_by_name = {tool.name: tool for tool in tools}
    for tool_call in tool_calls:
        tool_call_message = ToolCallPart(
            tool_call["function"]["name"], tool_call["function"]["arguments"]
        )
        function = tool_call["function"]
        if tool := tools_by_name.get(function["name"]):
            try:
                log("[agent] Running tool", tool.name, f"{tool_call_message=}")
                result = await tool._run(
                    tool_call_message,
                    ToolCallContext(
                        deps=context,
                        model=None,
                        usage=None,
                        prompt="",
                    ),
                )
                log("[agent] Tool result", result)
                tool_results.append(
                    {
                        "tool_call_id": tool_call["id"],
                        "output": str(result.content),
                    }
                )
            except Exception as e:
                log(
                    "[agent] Error processing tool call", str(e), traceback.format_exc()
                )
                tool_results.append(
                    {
                        "tool_call_id": tool_call["id"],
                        "output": f"Error processing tool call: {str(e)}",
                    }
                )
        else:
            tool_results.append(
                {
                    "tool_call_id": tool_call["id"],
                    "output": f"Unknown tool call: {tool_call['function']['name']}",
                }
            )
    return tool_results


def combine_examples_into_conversation(
    examples: list[MigrationExample],
    target: MigrationExample,
    system_prompt: str,
) -> list[dict]:
    messages = [{"role": "system", "content": system_prompt}]

    for example in examples:
        messages.extend(migrate_prompt(example))

    messages.extend(migrate_prompt(target))

    return messages


async def call_llm(
    client: DefaultClient,
    messages: list,
    tools: list[Tool],
    *,
    context: MigrationContext,
    temperature=0.1,
) -> tuple[dict, list[dict]]:
    """Call LLM for completions

    Returns the response and the messages so far
    """
    while True:
        response, messages = await client.generate_completion(
            messages=messages,
            tools=[await tool.prepare_tool_def(None) for tool in tools],
            temperature=temperature,
        )

        assistant_message = response["choices"][0]["message"]

        if not (tool_calls := assistant_message.get("tool_calls")):
            return response, messages

        tool_results = await handle_tool_calls(tools, tool_calls, context)

        messages.append(assistant_message)
        for result in tool_results:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": result["tool_call_id"],
                    "content": result["output"],
                }
            )

        for message in messages:
            if message.get("content") == "":
                del message["content"]


def filter_lines(text, match):
    return "\n".join(line for line in text.splitlines() if match in line)


async def subprocess_run(cmd, prefix=None, **kwargs) -> str:
    if not kwargs.get("stderr"):
        kwargs["stderr"] = subprocess.STDOUT
        kwargs["stdout"] = subprocess.PIPE
    check = False
    if "check" in kwargs:
        check = kwargs.pop("check")
    env = kwargs.pop("env", {})
    env = {**os.environ, "PYTHONUNBUFFERED": "1", **env}
    process = await asyncio.create_subprocess_exec(
        *cmd,
        **kwargs,
        env=env,
    )
    stdout = []
    if not prefix:
        prefix = cmd[0]
    while not process.stdout.at_eof():
        data = await process.stdout.readline()
        if not data:
            break
        line = data.decode().removesuffix("\n")
        log(f"[{prefix}] {line}")
        stdout.append(line)
    await process.wait()
    if check and process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, cmd)
    return "\n".join(stdout)


async def run(
    target_files: list[str],
    system_prompt,
    examples_dir,
    verify_cmd,
    pre_verify_cmd,
    log_stream,
    local_worktrees,
    llm_fakes,
    target_dir: str = "",
    target_basename: str = "",
    dont_create_evals: bool = False,
    tools: list[Tool] = None,
    goose_config: Optional[GooseConfig] = None,
):
    """Run the migration process on the target files.
    Args:
        target_files: List of files to migrate
        system_prompt: System prompt for the LLM
        examples_dir: Directory containing example migrations
        verify_cmd: Command to verify the migrated files
        pre_verify_cmd: Command to run before migration
        log_stream: Stream to write logs to
        local_worktrees: Whether to create worktrees locally
        dont_create_evals: If True, don't automatically create evaluations after successful migrations
    """
    if log_stream:
        LOG_STREAM.set(log_stream)

    source_git_root = Path(
        (
            await subprocess_run(["git", "rev-parse", "--show-toplevel"], check=True)
        ).strip()
    )
    source_start_point = (
        await subprocess_run(["git", "rev-parse", "HEAD"], check=True)
    ).strip()

    # If target_dir is specified, use it as the git root for the output
    if target_dir:
        target_dir_path = Path(target_dir)
        try:
            if not target_dir_path.exists():
                target_dir_path.mkdir(parents=True, exist_ok=True)

            target_git_root = Path(
                (
                    await subprocess_run(
                        ["git", "rev-parse", "--show-toplevel"],
                        check=True,
                        cwd=str(target_dir_path),
                    )
                ).strip()
            )
            start_point = (
                await subprocess_run(
                    ["git", "rev-parse", "HEAD"], check=True, cwd=str(target_git_root)
                )
            ).strip()

            target_dir_rel_path = target_dir_path.resolve().relative_to(
                target_git_root.resolve()
            )

            git_root = target_git_root
        except Exception as e:
            log(f"Error finding git repository: {e}")
            raise ValueError(
                f"Error: target_dir '{target_dir}' is not in a git repository."
            )
    else:
        # Use the source repository as the git root
        git_root = source_git_root
        start_point = source_start_point
        target_dir_rel_path = None

    # Get the relative paths of the target files
    targets_in_repo = [
        Path(target_file).resolve().relative_to(source_git_root)
        for target_file in target_files
    ]

    file_flat = FileGroup(files=target_files).group_name()
    file_flat += "-3"
    worktree_name = f"ai-migrator-worktree-{git_root.name}-{file_flat}"
    log(f"worktree_name: {worktree_name}")
    if local_worktrees:
        worktree_root = git_root.parent / "ai-migrator-worktrees" / worktree_name
    else:
        worktree_root = Path(tempfile.gettempdir()) / worktree_name
    branch = f"ai-migrator/{file_flat}"

    if os.getenv("AI_MIGRATE_DISABLE_WORKTREE"):
        worktree_root = git_root

        # First checkout main branch
        await subprocess_run(
            ["git", "checkout", "--force", "main"], 
            check=True, 
            cwd=str(worktree_root)
        )
        
        # Then get the commit hash for start_point
        start_point = (
            await subprocess_run(
                ["git", "rev-parse", "HEAD"], 
                check=True, 
                cwd=str(worktree_root)
            )
        ).strip()
        
        # Create the branch
        await subprocess_run(
            ["git", "checkout", "--force", "-B", branch, start_point],
            check=True,
            cwd=worktree_root,
        )
    else:
        os.environ["HUSKY"] = "0"
        
        # Get the current HEAD for the worktree
        start_point = (
            await subprocess_run(
                ["git", "rev-parse", "HEAD"], 
                check=True, 
                cwd=git_root
            )
        ).strip()

        if not worktree_root.exists():
            await subprocess_run(
                ["git", "worktree", "add", worktree_root, "HEAD"],
                check=True,
                cwd=git_root,
            )
            
        # Create the branch in the worktree
        await subprocess_run(
            ["git", "checkout", "--force", "-B", branch, start_point],
            check=True,
            cwd=worktree_root,
        )

    # If using target_dir, read files from original location instead of worktree
    target_root = source_git_root if target_dir else worktree_root
    targets_files = [target_root / target_in_repo for target_in_repo in targets_in_repo]

    return await _run(
        targets_files,
        system_prompt,
        examples_dir,
        verify_cmd,
        pre_verify_cmd,
        worktree_root,
        llm_fakes,
        dont_create_evals,
        target_dir=target_dir,
        target_dir_rel_path=target_dir_rel_path,
        target_basename=target_basename,
        tools=tools,
        goose_config=goose_config,
    )


@dataclass
class CodeBlock:
    filename: str | None
    code: str


@dataclass
class CodeResponseResult:
    code_blocks: list[CodeBlock]
    other_text: str


def extract_code_blocks(markdown, replacement="<code>") -> CodeResponseResult:
    lines = markdown.splitlines()
    filename = None
    line_it = iter(lines)
    result = CodeResponseResult([], "")
    other_text = []

    for line in line_it:
        if line.lstrip().startswith("### ") and line.count("`") == 2:
            start = line.find("`")
            end = line.find("`", start + 1)
            filename = line[start + 1 : end]
        elif line.lstrip().startswith("```"):
            code = []
            for line in line_it:
                if line.lstrip().startswith("```"):
                    break
                code.append(line)
            result.code_blocks.append(CodeBlock(filename, "\n".join(code)))
            filename = None
            other_text.append(replacement)
        else:
            other_text.append(line)

    if other_text:
        result.other_text = "\n".join(other_text)

    return result


class FailedPreVerification(Exception):
    pass

class FailedVerificationPartial(Exception):
    remaining_files: int

    def __init__(self, remaining_files: int):
        self.remaining_files = remaining_files


async def remove_worktree(worktree_root: str | Path):
    await asyncio.to_thread(shutil.rmtree, worktree_root, ignore_errors=True)


def build_messages(
    initial_messages: list[dict], iteration_messages: list[list[dict]]
) -> list[dict]:
    messages = initial_messages
    for iteration_message in iteration_messages:
        messages.extend(iteration_message)
    return messages


async def _run(
    target_files: list[str],
    system_prompt: str,
    examples_dir: str,
    verify_cmd: str,
    pre_verify_cmd: str,
    worktree_root: str | Path,
    llm_fakes: str | None,
    dont_create_evals: bool = False,
    target_dir: Path | str | None = None,
    target_dir_rel_path: Path | str | None = None,
    target_basename: str = None,
    tools: list[Tool] = None,
    goose_config: Optional[GooseConfig] = None,
):
    if llm_fakes:
        client = FakeLLMClient(llm_fakes)
    else:
        client = DefaultClient()

    verify_cmd = verify_cmd.split()

    examples = [*read_file_pairs_from(examples_dir)]
    if not examples:
        raise FileNotFoundError("No valid example pairs found in examples directory")

    system_prompt = Path(system_prompt).read_text()

    # TODO: Have some kind of configuration driven controls for how basename is transformed
    if target_basename:
        target_basename = (
            target_basename.replace("-", " ").replace("_", " ").title().replace(" ", "")
        )

    # Create target MigrationExample
    target_file_contents = []
    for i, target_file in enumerate(target_files):
        full_path = Path(target_file).absolute()

        if target_dir:
            read_path = Path(target_files[i]).absolute()
            short_name = full_path.name
            content = read_path.read_text()
        else:
            short_name = full_path.relative_to(worktree_root)
            content = full_path.read_text()

        target_file_contents.append(FileContent(name=str(short_name), content=content))

    target = MigrationExample(name=None, old_files=target_file_contents, new_files=[])

    messages = combine_examples_into_conversation(examples, target, system_prompt)
    all_files_to_verify = set()

    def build_verify_cmd(all_files_to_verify: set[str]):
        if target_dir:
            return [
                *verify_cmd,
                str(Path(target_dir_rel_path) / target_basename),
            ]
        return [
            *verify_cmd,
            *[str(Path(worktree_root) / f) for f in all_files_to_verify],
        ]

    full_verify_cmd = build_verify_cmd(all_files_to_verify)

    iteration_messages = []

    if pre_verify_cmd:
        log("Running pre-verification")
        try:
            await subprocess_run(
                [*pre_verify_cmd.split(), *target_files],
                prefix="pre-verify",
                check=True,
                cwd=worktree_root,
            )
        except subprocess.CalledProcessError:
            log(
                "Pre-verification failed. The migration cannot continue until all files pass the pre-verify step"
            )
            raise FailedPreVerification(f"file {target_files} failed pre-verification")

    if not target_dir:
        for target_file in target_files:
            os.remove(target_file)
            await subprocess_run(
                ["git", "add", target_file],
                cwd=worktree_root,
            )

    # Main migration attempts
    migration_successful = False
    written_files = set()
    
    for tries in range(int(os.getenv("AI_MIGRATE_MAX_TRIES", 10))):
        log(f"[agent] Running migration attempt {tries + 1}")

        messages = build_messages(messages, iteration_messages)
        log(f"[agent] Messages length: {client.count_tokens(messages)}")
        while 0 < client.max_context_tokens() < client.count_tokens(messages):
            log(f"Trimming iteration messages: {len(iteration_messages)}")
            messages = combine_examples_into_conversation(
                examples, target, system_prompt
            )
            examples = examples[1:]
            iteration_messages = iteration_messages[1:]
            messages = build_messages(messages, iteration_messages)

        context = MigrationContext(
            target_files=target_files,
            target_dir=Path(target_dir) if target_dir else None,
        )

        log(f"Calling LLM with {len(messages)} messages")
        response, messages = await call_llm(
            client, messages, tools or [], context=context
        )
        log(f"LLM done calling llm")

        response_text = response["choices"][0]["message"]["content"]
        parsed_result = extract_code_blocks(response_text)

        iteration_message = []
        if not parsed_result.code_blocks:
            iteration_message.append({"role": ROLE_ASSISTANT, "content": response_text})
            iteration_message.append(
                {
                    "role": ROLE_USER,
                    "content": "Include the full, complete code block. Do not omit any part of the file",
                }
            )
            continue

        log(f"Done parsing result")

        written_files = set()
        for code_block in parsed_result.code_blocks:
            migrated_code = un_escape_nbsp(code_block.code)

            if code_block.filename:
                written_files.add(code_block.filename)
                if target_dir:
                    output_path = (
                        Path(worktree_root)
                        / target_dir_rel_path
                        / target_basename
                        / code_block.filename
                    )
                else:
                    output_path = Path(worktree_root) / code_block.filename
                output_path.parent.mkdir(parents=True, exist_ok=True)

                with open(output_path, "w") as f:
                    f.write(migrated_code)

        log(f"Wrote {len(written_files)} files")

        all_files_to_verify |= written_files

        full_verify_cmd = build_verify_cmd(all_files_to_verify)

        log(f"Running verification: {full_verify_cmd}")
        verify_process = await asyncio.create_subprocess_exec(
            *full_verify_cmd,
            cwd=worktree_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = await verify_process.communicate()

        status = "pass" if verify_process.returncode == 0 else "fail"

        commit_message = f"Migration attempt {tries + 1} {status=}:\n\nLLM response:\n{parsed_result.other_text}"

        for file in written_files:
            if target_dir:
                file_path = (
                    Path(worktree_root) / target_dir_rel_path / target_basename / file
                )
                git_path = Path(file_path).relative_to(worktree_root)
                log(f"Adding {git_path}")
                await subprocess_run(
                    ["git", "add", git_path],
                    cwd=worktree_root,
                )
            else:
                await subprocess_run(
                    ["git", "add", file],
                    cwd=worktree_root,
                )

        log(f"Committing {commit_message}")
        await subprocess_run(
            ["git", "commit", "--allow-empty", "-m", commit_message],
            check=True,
            cwd=worktree_root,
            env={**os.environ, **environment_variables()},
        )

        verification_output = (stderr or stdout or b"").decode()
        await subprocess_run(
            [
                "git",
                "notes",
                "--ref=migrator-verify",
                "add",
                "-f",
                "-m",
                verification_output,
            ],
            check=True,
            cwd=worktree_root,
        )

        if verify_process.returncode == 0:
            log("Verification successful")

            if not dont_create_evals:
                original_contents = {}
                for target_file in target_files:
                    full_path = Path(target_file).absolute()
                    short_name = full_path.relative_to(worktree_root)
                    try:
                        with open(full_path, "r") as f:
                            original_contents[str(short_name)] = f.read()
                    except Exception as e:
                        log(f"Error reading {full_path}: {e}")

                transformed_contents = {}
                for file_path in written_files:
                    full_path = Path(worktree_root) / file_path
                    try:
                        with open(full_path, "r") as f:
                            transformed_contents[file_path] = f.read()
                    except Exception as e:
                        log(f"Error reading transformed file {full_path}: {e}")

                try:
                    project_dir = Path(examples_dir).parent

                    eval_manifest = Manifest(
                        files=[
                            FileEntry(filename=fname, result="pass")
                            for fname in written_files
                        ],
                        verify_cmd=" ".join(verify_cmd)
                        if isinstance(verify_cmd, list)
                        else verify_cmd,
                    )
                    if pre_verify_cmd:
                        eval_manifest.pre_verify_cmd = pre_verify_cmd

                    eval_dir = generate_eval_from_migration(
                        project_dir,
                        original_contents,
                        transformed_contents,
                        eval_manifest,
                    )
                    log(f"Created evaluation at {eval_dir}")
                except Exception as e:
                    log(f"Error creating evaluation: {e}")
                    log(f"Exception type: {type(e).__name__}")

            # await remove_worktree(worktree_root)
            migration_successful = True
            return True
        log("Verification failed:")
        for line in verification_output.splitlines():
            log(f"[verify] {line}")

        tool_call_extra = ""
        if tools:
            tool_call_extra = (
                f"Use the provided tools to help: {', '.join(tool.name for tool in tools)}"
                "Then apply the necessary changes to the code. Don't guess or assume functionality."
                "From now on, only re-write files, don't rename them."
            )

        iteration_message.append({"role": ROLE_ASSISTANT, "content": response_text})
        iteration_message.append(
            {
                "role": ROLE_USER,
                "content": f"The code did not compile. The error was: {verification_output}. "
                f"{tool_call_extra}",
            }
        )
        iteration_messages.append(iteration_message)

    if not migration_successful:
        log("Migration failed: Out of tries")

    # Run goose if configured, regardless of how the main loop exited
    if goose_config and not migration_successful:
        best_exit_code = float("inf")  # Track best exit code so far

        for i in range(goose_config.max_retries):
            log(f"Running migration attempt {i + 1} with Goose")

            goose_user_extra = ""
            if goose_config.user_prompt:
                goose_user_extra = Path(goose_config.user_prompt).read_text()

            directory_instructions = (
                f"You may only make changes to the files inside {target_dir_rel_path}/{target_basename}. Under no circumstances should you touch any files outside of this directory. If I detect that you do, I will be very disappointed in you and will switch to a smarter model."
                if target_dir
                else f"You may only make changes to the files: {', '.join(target_files)}. Under no circumstances should you touch any other files."
            )

            verify_cmd_str = " ".join(full_verify_cmd)

            log(f"Verify command: {verify_cmd_str}")

            goose_prompt = (
                "You are a helpful assistant for code migration. The migration is almost done but is not passing verification. "
                "With as few changes as possible, make the migration pass verification. "
                f"{directory_instructions} "
                "You may verify if the migration is correct by running the following command: "
                f"{verify_cmd_str} "
                "The verification output may be large. If you run into its size, pipe it to a file verification_output.txt and read it from there. "
                "Keep trying until the migration passes verification."
            )

            if goose_user_extra:
                goose_prompt += f"\n\n{goose_user_extra}"

            goose_command = [
                "goose",
                "run",
                "--text",
                goose_prompt,
                "--with-builtin",
                "developer",
            ]

            log(f"Running goose: {goose_command}")

            goose_process = await asyncio.create_subprocess_exec(
                *goose_command,
                cwd=worktree_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            async def kill_after_timeout():
                await asyncio.sleep(goose_config.timeout_seconds)
                if goose_process.returncode is None:
                    log(
                        f"[goose] Killing process after {goose_config.timeout_seconds} seconds timeout"
                    )
                    goose_process.kill()

            timeout_task = asyncio.create_task(kill_after_timeout())

            output_lines = []

            async def read_stream(stream, prefix):
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    decoded = line.decode().rstrip()
                    log(f"[{prefix}] {decoded}")
                    output_lines.append(decoded)

            stdout_task = asyncio.create_task(
                read_stream(goose_process.stdout, "goose")
            )
            stderr_task = asyncio.create_task(
                read_stream(goose_process.stderr, "goose-err")
            )

            try:
                await goose_process.wait()
                await stdout_task
                await stderr_task
                timeout_task.cancel()
            except asyncio.CancelledError:
                if goose_process.returncode is None:
                    goose_process.kill()
                stdout_task.cancel()
                stderr_task.cancel()
                raise

            goose_output = "\n".join(output_lines[-50:])

            if target_dir:
                await subprocess_run(
                    ["git", "reset"],
                    cwd=worktree_root,
                )

                git_path = Path(target_dir_rel_path) / target_basename
                await subprocess_run(
                    ["git", "add", git_path],
                    cwd=worktree_root,
                )
            else:
                await subprocess_run(
                    ["git", "reset"],
                    cwd=worktree_root,
                )

                for file in written_files:
                    await subprocess_run(
                        ["git", "add", file],
                        cwd=worktree_root,
                    )

            verify_process = await asyncio.create_subprocess_exec(
                *full_verify_cmd,
                cwd=worktree_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await verify_process.communicate()
            verification_output = (stderr or stdout or b"").decode()
            exit_code = verify_process.returncode

            if exit_code > best_exit_code and best_exit_code != 0:
                log(
                    f"Exit code {exit_code} is worse than previous best {best_exit_code}, resetting changes"
                )
                await subprocess_run(
                    ["git", "reset", "--hard"],
                    cwd=worktree_root,
                )
                continue

            best_exit_code = min(best_exit_code, exit_code)

            commit_message = f"Goose attempt {i + 1}, remaining tests: {exit_code}:\n\nGoose response:\n{goose_output}"

            await subprocess_run(
                ["git", "commit", "--allow-empty", "-m", commit_message],
                check=True,
                cwd=worktree_root,
                env={**os.environ, **environment_variables()},
            )

            await subprocess_run(
                [
                    "git",
                    "notes",
                    "--ref=migrator-verify",
                    "add",
                    "-f",
                    "-m",
                    verification_output,
                ],
                check=True,
                cwd=worktree_root,
            )

            if exit_code == 0:
                log("Verification successful")
                return True
            else:
                log(f"Verification failed with {exit_code} remaining test steps:")
                for line in verification_output.splitlines():
                    log(f"[verify] {line}")

        if best_exit_code != 0 and best_exit_code != float("inf"):
            raise FailedVerificationPartial(best_exit_code)

    if not migration_successful:
        raise ValueError("Migration failed: Out of tries")
