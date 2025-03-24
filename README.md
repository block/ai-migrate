# AI Migration Tool

This tool runs code migrations at scale. It is designed to be run in two phases:

Setup:
- Initialize a new project
- Add example pairs showing migration patterns
- Generate a system prompt for the migration task
- Create a verification script

Migration:
- Run the migration script: `ai-migrate migrate --project my-new-project`
- Check the status of the migration
- Check out a branch for manual fixes
- Merge all successful migrations

## Prerequisites

- [Hermit](https://cashapp.github.io/hermit/) installed

## Installation

1. Clone this repository:

```bash
gh repo clone block/ai_migrate
cd ai_migrate
```

2. Set up the development environment using Hermit:

```bash
hermit init
uv sync
```

This will:

- Initialize the Hermit environment with Python and required tools
- Install all necessary Python packages

3. Create your project:

```bash
# Basic project initialization
uv run ai-migrate init

# Or initialize from a PR (recommended)
uv run ai-migrate init <project_dir> --pr=<pr_number> --description="Brief description of migration"
```

4. Fill in the blanks. The above command generated some files you should edit:
   - `<project dir>/system_prompt.md`: Modify this to suit your migration details.
   - `examples/`: Add pairs of example files showing migration patterns. Use `uv run ai-migrate migrate --manage examples`
     to manage examples, including generating from git history or from a PR.

## Setting Up Examples

Add example pairs to your project's `examples/` directory.

Example structure:

```
project/
├── examples/
│   ├── Example1.old.java
│   ├── Example1.new.java
│   ├── Example2.old.java
│   └── Example2.new.java
```

## Usage

```bash
# Interactive CLI
uv run ai-migrate migrate
```

The interactive CLI provides a guided experience with:

- Interactive prompts for file paths and options
- Rich terminal output with colors and formatting
- Progress indicators during long-running operations
- Dialog-based selection for various options

### Key Commands

```bash
# Initialize a new project
uv run ai-migrate init

# Migrate files
uv run ai-migrate migrate [FILE_PATHS]

# Check migration status
uv run ai-migrate status

# Check out a branch for manual fixes
uv run ai-migrate checkout FILE_PATH

# Merge all successful migrations
uv run ai-migrate merge-branches

# Get help for a specific command
uv run ai-migrate migrate --help
```

### Project Selection

The interactive CLI now provides an easy way to select which migration project to use:

1. **Automatic Project Selection**:
   When you run a command without specifying a project directory, the CLI will:

   - First check the `AI_MIGRATE_PROJECT_DIR` environment variable
   - Then look for a `.ai-migrate` file in the current directory
   - If neither is found, show a selection dialog with available projects

2. **Project Selection Dialog**:

   - Shows all projects in the `projects/` directory
   - Allows you to select the appropriate project for your migration task
   - Remembers your selection for the current command

3. **Manual Project Specification**:
   - Use `--project-dir` option to specify a project directly, or use `--project` to specify a pre-configured project
   - Set the `AI_MIGRATE_PROJECT_DIR` environment variable for persistent selection
   - Create a `.ai-migrate` file in your repository for project-specific settings

This makes it easy to work with multiple migration projects without having to remember and type their paths each time.

This will look as input for the specified file and load it if it exists
as that or in the form of a .old. file. The script will write the output
to the same file and move the previous version to a .old. file if not .old.
previously existed. This way you can keep trying migrations having to move
files around.

## Command Comparison: Main Branch vs New CLI

Here's how commands from the main branch map to the new interactive CLI:

| Main Branch Command                                     | New Interactive CLI Command                                       | Description                                 |
| ------------------------------------------------------- | ----------------------------------------------------------------- | ------------------------------------------- |
| `uv run ai-migrate projects init <path>`                | `uv run ai-migrate init`                                          | Initialize a new project                    |
| `uv run ai-migrate examples setup <ref>`                | `uv run ai-migrate migrate --manage examples` then select "setup" | Set up examples from git history            |
| `uv run ai-migrate examples add <file>`                 | `uv run ai-migrate migrate --manage examples` then select "add"   | Add a file as an example                    |
| `uv run ai-migrate --files <file>`                      | `uv run ai-migrate migrate <file>`                                | Migrate a specific file                     |
| `uv run ai-migrate projects status`                     | `uv run ai-migrate status`                                        | Show migration status                       |
| `uv run ai-migrate projects run --manifest-file=<file>` | `uv run ai-migrate migrate --manifest-file=<file>`                | Run migration using a manifest file         |
| `uv run ai-migrate projects run --rerun-passed`         | `uv run ai-migrate migrate --rerun-passed`                        | Re-run migrations that have already passed  |
| `uv run ai-migrate projects run --max-workers=<num>`    | `uv run ai-migrate migrate --max-workers=<num>`                   | Set maximum number of parallel workers      |
| `uv run ai-migrate projects run --local-worktrees`      | `uv run ai-migrate migrate --local-worktrees`                     | Create worktrees alongside the git repo     |
| `uv run ai-migrate projects checkout <file>`            | `uv run ai-migrate checkout <file>`                               | Check out the branch for a failed migration |
| `uv run ai-migrate projects merge-branches`             | `uv run ai-migrate merge-branches`                                | Merge changes from migrator branches        |

### New Features in Interactive CLI

The new CLI adds these capabilities not present in the main branch:

1. **PR-Based Initialization**:

   ```bash
   uv run ai-migrate init
   # Then follow interactive prompts for PR-based setup
   ```

2. **Example Management UI**:

   ```bash
   uv run ai-migrate migrate --manage examples
   # Interactive dialog for listing, adding, or generating examples
   ```

3. **System Prompt Management**:

   ```bash
   uv run ai-migrate migrate --manage system-prompt
   # Interactive dialog for viewing, editing, or generating system prompts
   ```

4. **Automatic Evaluation Generation**:

   ```bash
   # Disable automatic evaluation generation
   uv run ai-migrate migrate --dont-create-evals <file_paths>

   # Manage evaluations
   uv run ai-migrate migrate --manage evals
   ```

5. **Rich Help System**:
   ```bash
   uv run ai-migrate --help
   uv run ai-migrate <command> --help
   ```

## Development

The project uses Hermit to manage Python versions and development tools. Available tools:

- Python 3.12
- Black (code formatting)
- Ruff (linting)
- MyPy (type checking)
- Pytest (testing)

To activate the Hermit environment in your shell:

```bash
eval "$(./bin/hermit env)"
```

## Documentation

Additional documentation is available in the `docs/` directory:

- [Evaluation Runner](docs/eval_runner.md) - Documentation for the evaluation runner system
- [Automatic Evaluation Generation](docs/eval_improvement.md) - Documentation for the automatic evaluation generation feature

## AI-Powered Project Setup

The tool now supports AI-powered project setup using GitHub PRs:

1. **PR-Based Project Initialization**:

   ```bash
   # Using the interactive CLI
   uv run ai-migrate init
   # Then follow the prompts

   ```

   This will:

   - Generate a system prompt based on the PR description and changes
   - Extract example patterns from the PR changes

2. **Generate Examples from PR**:

   ```bash
   # Using the interactive CLI
   uv run ai-migrate migrate --manage examples
   # Then select "from-pr" and follow the prompts
   ```

   This will analyze the PR changes and extract representative examples of the migration pattern.

3. **Manage System Prompt**:
   ```bash
   # Using the interactive CLI
   uv run ai-migrate migrate --manage system-prompt
   # Then select an action (view, edit, or generate) and follow the prompts
   ```
   This allows you to view, edit, or generate a new system prompt for your migration project.

## Interactive CLI

The new interactive CLI provides a more user-friendly experience with:

1. **Rich Terminal UI**:

   - Colorized output for better readability
   - Progress bars and spinners for long-running operations
   - Formatted panels and tables for displaying information

2. **Interactive Prompts**:

   - File path completion for easier navigation
   - Selection dialogs for choosing options
   - Yes/no confirmations for important decisions

3. **Guided Workflows**:

   - Step-by-step guidance through complex operations
   - Clear error messages and recovery options
   - Contextual help and suggestions

4. **Available Commands**:
   - `init` - Initialize a new migration project
   - `migrate` - Migrate one or more files or manage project resources
     - Use `--manage examples` to manage example files
     - Use `--manage system-prompt` to view or edit the system prompt
     - Use `--manage evals` to manage evaluation test cases
     - Use `--manifest-file` to specify a manifest file for batch processing
     - Use `--rerun-passed` to re-run migrations that have already passed
     - Use `--max-workers` to set the maximum number of parallel workers
     - Use `--local-worktrees` to create worktrees alongside the git repo
     - Use `--dont-create-evals` to disable automatic evaluation generation
   - `status` - Show the status of migration projects
     - See which files are passing, failing, or have not been processed
   - `checkout` - Check out the branch for a failed migration attempt
     - Allows you to manually fix a migration that failed
   - `merge-branches` - Merge changes from migrator branches
     - Consolidate all successful migrations

To use the interactive CLI, simply run:

```bash
uv run ai-migrate
```

For specific commands:

```bash
# Initialize a new project
uv run ai-migrate init

# Migrate files
uv run ai-migrate migrate [FILE_PATHS]

# Check migration status
uv run ai-migrate status

# Check out a branch for manual fixes
uv run ai-migrate checkout FILE_PATH

# Merge all successful migrations
uv run ai-migrate merge-branches

# Get help for a specific command
uv run ai-migrate migrate --help
```

## Automatic Evaluation Generation

The tool now automatically creates evaluation test cases from successful migrations. This helps build a comprehensive test suite and ensures that future versions of the migration system continue to work correctly.

### How It Works

1. When a migration succeeds (passes verification), the system:
   - Captures the original source files before migration
   - Creates a new directory in the `evals` directory with a timestamp-based name
   - Saves the original files in the `source` subdirectory
   - Creates a manifest file with the verification command and file information

2. These evaluations can then be used to:
   - Test future versions of the migration system
   - Ensure that regressions don't occur
   - Benchmark performance and accuracy

### Usage

By default, evaluations are automatically created for every successful migration. You can:

```bash
# Disable automatic evaluation creation
uv run ai-migrate migrate --dont-create-evals <file_paths>

# Manage evaluations
uv run ai-migrate migrate --manage evals
```

The evaluation management interface allows you to:
- List existing evaluations with details like file count and creation date
- Generate evaluations from a GitHub Pull Request
- Generate evaluations from recent successful migrations
