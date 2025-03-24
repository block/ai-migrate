# Automatic Evaluation Generation

The system now automatically creates evaluation test cases from successful migrations. This behavior is enabled by default and can be disabled using the `--dont-create-evals` flag:

```bash
ai-migrate migrate --dont-create-evals <file_paths>
```

Each successful migration will generate a new evaluation in the project's `evals` directory with:
- The original source files
- The manifest used for the migration
- The verification command that was used

This ensures that all successful migrations contribute to the test suite, improving coverage and helping to catch regressions.

## Managing Evaluations

You can also manage evaluations using the CLI:

```bash
ai-migrate migrate --manage evals
```

This provides options to:
- **List existing evaluations**: View all evaluations in the project with details like file count and creation date
- **Generate evaluations from a PR**: Create evaluations based on a GitHub Pull Request
- **Generate evaluations from recent migrations**: Create evaluations from recent successful migrations (coming soon)

## How Automatic Evaluation Works

When a migration succeeds (passes verification), the system:

1. Captures the original source files before migration
2. Captures the transformed files after migration
3. Creates a new directory in the `evals` directory with a timestamp-based name
4. Saves the original files in the `source` subdirectory
5. Creates a manifest file with the verification command and file information

These evaluations can then be used to:
- Test future versions of the migration system
- Ensure that regressions don't occur
- Benchmark performance and accuracy

## Disabling Automatic Evaluation

If you don't want to automatically create evaluations (for example, during development or testing), use the `--dont-create-evals` flag:

```bash
ai-migrate migrate --dont-create-evals <file_paths>
```

This will skip the evaluation creation step while still performing the migration as usual.