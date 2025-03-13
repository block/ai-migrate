# AI Migration Eval Runner

The eval runner is a tool for running evaluations on AI migration projects. It helps validate that migrations are working correctly by running them against test repositories.

## Usage

```bash
# Run all available projects
ai-migrate-eval

# Run specific projects
ai-migrate-eval project1 project2

# Run with verbose output
ai-migrate-eval -v

# Set custom log level
ai-migrate-eval --log-level DEBUG

# Log to a file
ai-migrate-eval --log-file eval_results.log
```

## Command Line Options

- `projects`: Space-separated list of project names to evaluate. If none provided, all projects will be evaluated.
- `-v, --verbose`: Enable verbose output, showing all command outputs and detailed logs
- `--log-level`: Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `--log-file`: Log to a file in addition to console

## Output

The eval runner provides detailed information about the evaluation process:

- Project discovery
- Evaluation progress for each project
- Detailed logs for command execution (in verbose mode)
- Comprehensive error logs for failed migrations
- Summary of results

## Example

```bash
# Run evaluation for the kotest-migration project with verbose output
ai-migrate-eval kotest-migration -v

# Run all projects and save logs to a file
ai-migrate-eval --log-file all_evals.log
```

## Understanding Results

The evaluation results include:
- Total number of projects evaluated
- Number of evaluations run
- Number of passed and failed evaluations
- Detailed logs for each failed evaluation

A non-zero exit code is returned if any evaluations fail.
