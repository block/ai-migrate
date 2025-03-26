import asyncio
import contextvars
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
import subprocess
import json
from typing import Any, Iterable, Optional

from ai_migrate.llm_providers import DefaultClient
from .fake_llm_client import FakeLLMClient
from .git_identity import environment_variables
from .manifest import FileGroup, FileEntry, Manifest
from .resolve_symbols import get_symbol_definition
from .eval_generator import generate_eval_from_migration

FN_LOOKUP_SYMBOL = "lookup_symbol_definition"

LOOKUP_SYMBOL_PROMPT = (
    "Do not include any explanations or comments outside the code block.\n"
    "Do not assume functionality of classes or functions that you haven't seen in the examples. "
    f"Instead use the provided tool '{FN_LOOKUP_SYMBOL}' to look up the definition of a symbol.\n"
    "You want to produce code that you can guarantee to compile, so use this tool whenever you are unsure."
)

if os.environ.get("AI_MIGRATE_DISABLE_TOOLS", "").lower() in ("true", "1", "yes"):
    LOOKUP_SYMBOL_PROMPT = ""

SYSTEM_MESSAGE = (
    "You are an expert at migrating source code to modern standards. "
    "For each example pair you see, understand the patterns of modernization applied. "
    "Then apply similar modernization patterns to the target code while preserving its functionality. "
    "Provide only the migrated code between triple backticks (```). "
    f"{LOOKUP_SYMBOL_PROMPT}"
)


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": FN_LOOKUP_SYMBOL,
            "description": "Get the definition of a symbol from the source code needed to complete the migration",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "The symbol name to look up (function, constant, etc)",
                    },
                    "import": {
                        "type": "string",
                        "description": "The import statement to add to the source code to get to this symbol",
                    },
                },
                "required": ["symbol", "import"],
            },
        },
    }
]
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


def handle_tool_calls(tool_calls: list[dict[str, Any]]) -> list[dict[str, str]]:
    tool_results = []
    for tool_call in tool_calls:
        function = tool_call["function"]
        if function["name"] == FN_LOOKUP_SYMBOL:
            try:
                args = json.loads(function["arguments"])
                symbol = args["symbol"]
                package = args["import"]
                definition = (
                    get_symbol_definition(symbol, package)
                    or "Symbol not found. It might not be available in this repository."
                )
                log(f"Looking up symbol: {symbol}")
                log(">>", definition)

                tool_results.append(
                    {
                        "tool_call_id": tool_call["id"],
                        "output": definition,
                    }
                )
            except Exception as e:
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


def messages_and_tools(
    examples: list[MigrationExample],
    target: MigrationExample,
    system_prompt: str,
) -> tuple[list, list]:
    messages = [{"role": "system", "content": system_prompt}]

    for example in examples:
        messages.extend(migrate_prompt(example))

    messages.extend(migrate_prompt(target))

    # Check if tool calling should be disabled
    if os.environ.get("AI_MIGRATE_DISABLE_TOOLS", "").lower() in ("true", "1", "yes"):
        return messages, []
    else:
        return messages, TOOL_DEFINITIONS


async def call_llm(
    client: DefaultClient, messages: list, tools: list, temperature=0.1
) -> tuple[dict, list[dict]]:
    """Call LLM for completions

    Returns the response and the messages so far
    """
    while True:
        response, messages = await client.generate_completion(
            messages=messages, tools=tools, temperature=temperature
        )

        assistant_message = response["choices"][0]["message"]

        if not (tool_calls := assistant_message.get("tool_calls")):
            return response, messages

        tool_results = handle_tool_calls(tool_calls)

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
    worktree_name = f"ai-migrator-worktree-{git_root.name}-{file_flat}"
    if local_worktrees:
        worktree_root = git_root.parent / "ai-migrator-worktrees" / worktree_name
    else:
        worktree_root = Path(tempfile.gettempdir()) / worktree_name
    branch = f"ai-migrator/{file_flat}"

    if not worktree_root.exists():
        await subprocess_run(
            ["git", "worktree", "add", worktree_root, "HEAD"],
            check=True,
            cwd=git_root,
        )
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
    target_files,
    system_prompt,
    examples_dir,
    verify_cmd,
    pre_verify_cmd,
    worktree_root,
    llm_fakes,
    dont_create_evals=False,
    target_dir=None,
    target_dir_rel_path=None,
    target_basename=None,
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

    messages, tools = messages_and_tools(examples, target, system_prompt)
    all_files_to_verify = set()

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

    for tries in range(int(os.getenv("AI_MIGRATE_MAX_TRIES", 10))):
        log(f"[agent] Running migration attempt {tries + 1}")

        messages = build_messages(messages, iteration_messages)
        log(f"[agent] Messages length: {client.count_tokens(messages)}")
        while 0 < client.max_context_tokens() < client.count_tokens(messages):
            log(f"Trimming iteration messages: {len(iteration_messages)}")
            # Fall back to 3 examples + trim iterations 1 at a time.
            messages, _ = messages_and_tools(examples[:3], target, system_prompt)
            iteration_messages = iteration_messages[1:]
            messages = build_messages(messages, iteration_messages)

        response, messages = await call_llm(client, messages, tools)

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

        all_files_to_verify |= written_files

        # Add the files to verify with the correct paths
        if target_dir:
            full_verify_cmd = [
                *verify_cmd,
                str(Path(target_dir_rel_path) / target_basename),
            ]
        else:
            full_verify_cmd = [
                *verify_cmd,
                *[str(Path(worktree_root) / f) for f in all_files_to_verify],
            ]

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
                await subprocess_run(
                    ["git", "add", git_path],
                    cwd=worktree_root,
                )
            else:
                await subprocess_run(
                    ["git", "add", file],
                    cwd=worktree_root,
                )

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

            await remove_worktree(worktree_root)
            break
        log("Verification failed:")
        for line in verification_output.splitlines():
            log(f"[verify] {line}")

        lookup_symbol_prompt = (
            f"Use the {FN_LOOKUP_SYMBOL} tool to find the definition of any symbols related to this problem. "
            "Then apply the necessary changes to the code. Don't guess or assume functionality."
            "From now on, only re-write files, don't rename them."
        )
        if os.environ.get("AI_MIGRATE_DISABLE_TOOLS", "").lower() in (
            "true",
            "1",
            "yes",
        ):
            lookup_symbol_prompt = ""

        iteration_message.append({"role": ROLE_ASSISTANT, "content": response_text})
        iteration_message.append(
            {
                "role": ROLE_USER,
                "content": f"The code did not compile. The error was: {verification_output}. "
                f"{lookup_symbol_prompt}",
            }
        )
        iteration_messages.append(iteration_message)

    else:
        raise ValueError("Migration failed: Out of tries")
