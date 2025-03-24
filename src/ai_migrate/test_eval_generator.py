import tempfile
import json
import subprocess
from pathlib import Path

import pytest

from ai_migrate.migrate import _run
from ai_migrate.fake_llm_client import FakeLLMClient
from ai_migrate.eval_generator import (
    generate_eval_from_migration,
    generate_eval_from_pr,
)


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory with examples and evals folders."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_dir = Path(temp_dir) / "project"
        examples_dir = project_dir / "examples"
        evals_dir = project_dir / "evals"

        examples_dir.mkdir(parents=True)
        evals_dir.mkdir(parents=True)

        old_file = examples_dir / "example.old.py"
        new_file = examples_dir / "example.new.py"

        with open(old_file, "w") as f:
            f.write('def old_function():\n    print("This is the old version")\n')

        with open(new_file, "w") as f:
            f.write('def new_function():\n    print("This is the new version")\n')

        system_prompt_file = project_dir / "system_prompt.md"
        with open(system_prompt_file, "w") as f:
            f.write("You are an expert at migrating code. Follow these patterns.")

        yield project_dir


@pytest.fixture
def temp_worktree():
    """Create a temporary directory to simulate a git worktree."""
    with tempfile.TemporaryDirectory() as temp_dir:
        worktree_dir = Path(temp_dir) / "worktree"
        worktree_dir.mkdir()

        test_file = worktree_dir / "example.py"
        with open(test_file, "w") as f:
            f.write(
                'def old_function():\n    print("This is the original version")\n    return "Old implementation"\n'
            )

        yield worktree_dir


@pytest.fixture
def fake_llm_client():
    """Create a FakeLLMClient with test responses."""
    responses_dir = Path(__file__).parent / "test" / "eval_test_data"
    return FakeLLMClient(responses_dir)


@pytest.mark.asyncio
async def test_eval_generation_with_flag(
    monkeypatch, temp_project_dir, temp_worktree, fake_llm_client
):
    """Test that evaluations are not created when the dont_create_evals flag is True."""

    monkeypatch.setattr("ai_migrate.migrate.DefaultClient", lambda: fake_llm_client)

    async def mock_subprocess_run(*args, **kwargs):
        return "mocked output"

    monkeypatch.setattr("ai_migrate.migrate.subprocess_run", mock_subprocess_run)

    class MockProcess:
        returncode = 0
        stdout = None

        async def communicate(self):
            return b"", b""

    async def mock_create_subprocess_exec(*args, **kwargs):
        return MockProcess()

    monkeypatch.setattr("asyncio.create_subprocess_exec", mock_create_subprocess_exec)

    target_file = temp_worktree / "example.py"
    with open(target_file, "w") as f:
        f.write('def original_function():\n    print("Original code")\n')

    verify_cmd = "echo success"

    await _run(
        target_files=[target_file],
        system_prompt=temp_project_dir / "system_prompt.md",
        examples_dir=temp_project_dir / "examples",
        verify_cmd=verify_cmd,
        pre_verify_cmd=None,
        worktree_root=temp_worktree,
        llm_fakes=None,
        dont_create_evals=True,
    )

    evals_dir = temp_project_dir / "evals"
    assert len(list(evals_dir.iterdir())) == 0


@pytest.mark.asyncio
async def test_eval_generation_without_flag(
    monkeypatch, temp_project_dir, temp_worktree, fake_llm_client
):
    """Test that evaluations are created when the dont_create_evals flag is False."""

    monkeypatch.setattr("ai_migrate.migrate.DefaultClient", lambda: fake_llm_client)

    async def mock_subprocess_run(*args, **kwargs):
        return "mocked output"

    monkeypatch.setattr("ai_migrate.migrate.subprocess_run", mock_subprocess_run)

    class MockProcess:
        returncode = 0
        stdout = None

        async def communicate(self):
            return b"", b""

    async def mock_create_subprocess_exec(*args, **kwargs):
        return MockProcess()

    monkeypatch.setattr("asyncio.create_subprocess_exec", mock_create_subprocess_exec)

    target_file = temp_worktree / "example.py"
    with open(target_file, "w") as f:
        f.write('def original_function():\n    print("Original code")\n')

    verify_cmd = "echo success"

    await _run(
        target_files=[target_file],
        system_prompt=temp_project_dir / "system_prompt.md",
        examples_dir=temp_project_dir / "examples",
        verify_cmd=verify_cmd,
        pre_verify_cmd=None,
        worktree_root=temp_worktree,
        llm_fakes=None,
        dont_create_evals=False,
    )

    evals_dir = temp_project_dir / "evals"
    eval_dirs = list(evals_dir.iterdir())
    assert len(eval_dirs) == 1

    eval_dir = eval_dirs[0]
    assert (eval_dir / "source").exists()
    assert (eval_dir / "manifest.json").exists()

    source_files = list((eval_dir / "source").iterdir())
    assert len(source_files) == 1
    assert source_files[0].name == "example.py"

    with open(source_files[0]) as f:
        pass

    with open(eval_dir / "manifest.json") as f:
        manifest = json.load(f)

        assert "files" in manifest
        assert len(manifest["files"]) > 0
        assert manifest["verify_cmd"] == verify_cmd


def test_generate_eval_from_migration():
    """Test the generate_eval_from_migration function directly."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_dir = Path(temp_dir)
        evals_dir = project_dir / "evals"
        evals_dir.mkdir()

        source_files = {"example.py": 'def old_function():\n    print("Original")\n'}
        transformed_files = {
            "example.py": 'def new_function():\n    print("Transformed")\n'
        }

        from ai_migrate.manifest import Manifest, FileEntry

        manifest = Manifest(
            files=[FileEntry(filename="example.py", result="pass")],
            verify_cmd="echo success",
        )

        eval_dir = generate_eval_from_migration(
            project_dir, source_files, transformed_files, manifest
        )

        assert eval_dir.exists()
        assert (eval_dir / "source").exists()
        assert (eval_dir / "manifest.json").exists()

        with open(eval_dir / "source" / "example.py") as f:
            content = f.read()
        assert content == source_files["example.py"]

        with open(eval_dir / "manifest.json") as f:
            saved_manifest = json.load(f)

        assert "files" in saved_manifest
        assert len(saved_manifest["files"]) == 1
        assert saved_manifest["files"][0]["filename"] == "example.py"
        assert saved_manifest["files"][0]["result"] == "pass"
        assert saved_manifest["verify_cmd"] == "echo success"


@pytest.mark.asyncio
async def test_generate_eval_from_pr_error_handling(monkeypatch):
    """Test error handling in generate_eval_from_pr function."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_dir = Path(temp_dir)
        evals_dir = project_dir / "evals"
        evals_dir.mkdir()

        class MockProcess:
            def __init__(self, cmd):
                self.cmd = cmd

                if cmd[0] == "git" and cmd[1] == "clone":
                    self.returncode = 1
                    self._stderr = b"Failed to clone repository"
                else:
                    self.returncode = 0
                    if cmd[0] == "gh" and cmd[1] == "pr" and cmd[2] == "view":
                        self._stdout = json.dumps(
                            {
                                "title": "Test PR",
                                "headRepository": {
                                    "name": "test-repo",
                                    "owner": {"login": "test-user"},
                                },
                                "files": [{"path": "test.py"}],
                                "baseRefOid": "abc123",
                            }
                        ).encode()
                    else:
                        self._stdout = b""
                    self._stderr = b""

            async def communicate(self):
                return getattr(self, "_stdout", b""), getattr(self, "_stderr", b"")

        async def mock_create_subprocess_exec(*args, **kwargs):
            return MockProcess(args)

        monkeypatch.setattr(
            "asyncio.create_subprocess_exec", mock_create_subprocess_exec
        )

        with pytest.raises(subprocess.CalledProcessError):
            await generate_eval_from_pr("test-pr-url", str(project_dir))

        eval_dirs = list(evals_dir.iterdir())
        assert len(eval_dirs) > 0
        eval_dir = eval_dirs[0]
        assert eval_dir.exists()
        assert (eval_dir / "source").exists()
        assert (eval_dir / "manifest.json").exists()
