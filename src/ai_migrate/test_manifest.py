import tempfile

from ai_migrate.manifest import Manifest
from .manifest import Directory, FileGroup
from pathlib import Path


def test_valid_manifest():
    json = """
{
  "eval_target_repo_ref": "",
  "files": [
    {
      "filename": "service/src/test/kotlin/com/squareup/cash/enforcementactions/tasks/PreviouslyDeactivatedFilterTest.kt",
      "result": "?"
    },
    {
      "filename": "service/src/test/kotlin/com/squareup/cash/enforcementactions/tasks/PreviouslyNotifiedFilterTest.kt",
      "result": "?"
    }
  ],
  "system_prompt": "{project_dir}/system_prompt.md",
  "verify_cmd": "{py} {project_dir}/verify.py",
  "pre_verify_cmd": "{py} {project_dir}/verify.py --pre",
  "time": "2025-02-10T11:26:33.969758"
}
    """
    Manifest.model_validate_json(json)


def test_valid_manifest_groups():
    json = """
{
  "eval_target_repo_ref": "",
  "files": [
    {
        "files": [
          "service/src/test/kotlin/com/squareup/cash/enforcementactions/tasks/Test1.kt",
          "service/src/test/kotlin/com/squareup/cash/enforcementactions/tasks/PreviouslyDeactivatedFilterTest.kt"
        ],
        "result": "?"
    },
    {
      "filename": "service/src/test/kotlin/com/squareup/cash/enforcementactions/tasks/PreviouslyNotifiedFilterTest.kt",
      "result": "?"
    },
    {
      "dir": "service/src/test/kotlin/com/squareup/cash/enforcementactions/models",
      "result": "?"
    },
    {
      "dir": "service/src/test/kotlin/com/squareup/cash/enforcementactions/utils",
      "glob": "**/*.kt",
      "result": "?"
    }
  ],
  "system_prompt": "{project_dir}/system_prompt.md",
  "verify_cmd": "{py} {project_dir}/verify.py",
  "pre_verify_cmd": "{py} {project_dir}/verify.py --pre",
  "time": "2025-02-10T11:26:33.969758"
}
    """
    manifest = Manifest.model_validate_json(json)
    assert len(manifest.files) == 4

    # Check the structure of the group name rather than the exact hash
    group_name = manifest.files[0].group_name()
    assert group_name.startswith(
        "service__src__test__kotlin__com__squareup__cash__enforcementactions__tasks__Test1.kt-"
    )
    assert len(group_name.split("-")[1]) == 8  # Check that the hash is 8 characters

    assert (
        manifest.files[1].group_name()
        == "service__src__test__kotlin__com__squareup__cash__enforcementactions__tasks__PreviouslyNotifiedFilterTest.kt"
    )

    # Check the Directory group_name format
    dir_group_name = manifest.files[2].group_name()
    assert dir_group_name.startswith(
        "service__src__test__kotlin__com__squareup__cash__enforcementactions__models-"
    )
    assert len(dir_group_name.split("-")[1]) == 8  # Check that the hash is 8 characters

    # Check the Directory group_name with custom glob
    dir_glob_group_name = manifest.files[3].group_name()
    assert dir_glob_group_name.startswith(
        "service__src__test__kotlin__com__squareup__cash__enforcementactions__utils-"
    )
    assert (
        len(dir_glob_group_name.split("-")[1]) == 8
    )  # Check that the hash is 8 characters
    # The hash should be different because the glob pattern is different
    assert dir_glob_group_name.split("-")[1] != dir_group_name.split("-")[1]


def test_normalize_files():
    """Test that Directory.to_file_group correctly converts Directory objects to FileGroup objects."""

    # Create a temporary directory structure for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a directory structure
        test_dir = Path(temp_dir) / "test_dir"
        test_dir.mkdir()

        # Create some test files with different extensions
        (test_dir / "file1.txt").write_text("test content 1")
        (test_dir / "file2.txt").write_text("test content 2")
        (test_dir / "file3.py").write_text("test content 3")

        # Create a subdirectory with files
        sub_dir = test_dir / "subdir"
        sub_dir.mkdir()
        (sub_dir / "file4.txt").write_text("test content 4")
        (sub_dir / "file5.py").write_text("test content 5")

        # Create Directory objects using different glob patterns
        dir1 = Directory(dir=str(test_dir), result="?")  # Default glob (all files)
        dir2 = Directory(
            dir=str(test_dir), glob="**/*.py", result="py_only"
        )  # Only Python files

        # Convert Directory objects to FileGroup objects
        file_group1 = dir1.to_file_group()
        file_group2 = dir2.to_file_group()

        # Check that the Directory objects were converted to FileGroup objects
        assert isinstance(file_group1, FileGroup)
        assert isinstance(file_group2, FileGroup)

        # Check that the first FileGroup contains all files (default glob)
        assert len(file_group1.files) == 5

        # Check that the second FileGroup contains only Python files
        assert len(file_group2.files) == 2
        py_files = set(file_group2.files)
        expected_py_files = {str(test_dir / "file3.py"), str(sub_dir / "file5.py")}
        assert py_files == expected_py_files

        # Check that the result was preserved
        assert file_group1.result == "?"
        assert file_group2.result == "py_only"


def test_directory_to_file_group():
    """Test that Directory.to_file_group correctly converts a Directory to a FileGroup."""
    from .manifest import Directory, flatten, sha256
    import tempfile
    from pathlib import Path

    # Create a temporary directory structure for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a directory structure
        test_dir = Path(temp_dir) / "test_dir"
        test_dir.mkdir()

        # Create some test files with different extensions
        (test_dir / "file1.txt").write_text("test content 1")
        (test_dir / "file2.txt").write_text("test content 2")
        (test_dir / "file3.py").write_text("test content 3")

        # Create a subdirectory with files
        sub_dir = test_dir / "subdir"
        sub_dir.mkdir()
        (sub_dir / "file4.txt").write_text("test content 4")
        (sub_dir / "file5.py").write_text("test content 5")

        # Test the group_name method
        directory = Directory(dir=str(test_dir), result="test_result")
        expected_hash = sha256(f"{str(test_dir)}:**/*".encode()).hexdigest()[:8]
        expected_group_name = f"{flatten(str(test_dir))}-{expected_hash}"
        assert directory.group_name() == expected_group_name

        # Test with a different glob pattern
        directory_py = Directory(dir=str(test_dir), glob="**/*.py", result="py_only")
        expected_hash_py = sha256(f"{str(test_dir)}:**/*.py".encode()).hexdigest()[:8]
        expected_group_name_py = f"{flatten(str(test_dir))}-{expected_hash_py}"
        assert directory_py.group_name() == expected_group_name_py

        # Test with default glob pattern (all files)
        directory = Directory(dir=str(test_dir), result="test_result")
        file_group = directory.to_file_group()

        # Check that the FileGroup contains all files
        assert len(file_group.files) == 5

        # Check that the paths are correct
        file_paths = set(file_group.files)
        expected_paths = {
            str(test_dir / "file1.txt"),
            str(test_dir / "file2.txt"),
            str(test_dir / "file3.py"),
            str(sub_dir / "file4.txt"),
            str(sub_dir / "file5.py"),
        }
        assert file_paths == expected_paths

        # Check that the result was preserved
        assert file_group.result == "test_result"

        # Test with a specific glob pattern (only Python files)
        directory_py = Directory(dir=str(test_dir), glob="**/*.py", result="py_only")
        file_group_py = directory_py.to_file_group()

        # Check that the FileGroup contains only Python files
        assert len(file_group_py.files) == 2

        # Check that the paths are correct
        py_file_paths = set(file_group_py.files)
        expected_py_paths = {str(test_dir / "file3.py"), str(sub_dir / "file5.py")}
        assert py_file_paths == expected_py_paths

        # Check that the result was preserved
        assert file_group_py.result == "py_only"

        # Test with a more specific glob pattern (only txt files in the root directory)
        directory_txt_root = Directory(
            dir=str(test_dir), glob="*.txt", result="txt_root"
        )
        file_group_txt_root = directory_txt_root.to_file_group()

        # Check that the FileGroup contains only txt files in the root directory
        assert len(file_group_txt_root.files) == 2

        # Check that the paths are correct
        txt_root_file_paths = set(file_group_txt_root.files)
        expected_txt_root_paths = {
            str(test_dir / "file1.txt"),
            str(test_dir / "file2.txt"),
        }
        assert txt_root_file_paths == expected_txt_root_paths


def test_directory_with_multiple_extensions():
    """Test that Directory.to_file_group correctly handles glob patterns with multiple extensions."""
    from .manifest import Directory
    import tempfile
    from pathlib import Path

    # Create a temporary directory structure for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a directory structure
        test_dir = Path(temp_dir) / "test_dir"
        test_dir.mkdir()

        # Create files with different extensions
        (test_dir / "file1.kt").write_text("kotlin file")
        (test_dir / "file2.js").write_text("javascript file")
        (test_dir / "file3.py").write_text("python file")
        (test_dir / "file4.txt").write_text("text file")

        # Create a subdirectory with files
        sub_dir = test_dir / "subdir"
        sub_dir.mkdir()
        (sub_dir / "file5.kt").write_text("another kotlin file")
        (sub_dir / "file6.js").write_text("another javascript file")
        (sub_dir / "file7.py").write_text("another python file")

        # Test with a glob pattern that matches multiple extensions
        directory = Directory(
            dir=str(test_dir), glob="**/*.{kt,js}", result="kt_js_files"
        )
        file_group = directory.to_file_group()

        # Print debug information
        print(f"Directory: {test_dir}")
        print(f"Files found: {file_group.files}")

        # Check that the FileGroup contains only .kt and .js files
        assert len(file_group.files) == 4

        # Check that the paths are correct
        file_paths = set(file_group.files)
        expected_paths = {
            str(test_dir / "file1.kt"),
            str(test_dir / "file2.js"),
            str(sub_dir / "file5.kt"),
            str(sub_dir / "file6.js"),
        }
        assert file_paths == expected_paths

        # Check that the result was preserved
        assert file_group.result == "kt_js_files"


def test_manifest_with_target_dir():
    """Test that a manifest with a target_dir is correctly parsed."""
    from .manifest import Manifest

    json = """
{
  "eval_target_repo_ref": "",
  "migrate_repo_ref": "",
  "files": [
    {
      "filename": "src/main/java/com/example/App.java",
      "result": "?"
    }
  ],
  "target_dir": "/path/to/target/repo",
  "system_prompt": "{project_dir}/system_prompt.md",
  "verify_cmd": "{py} {project_dir}/verify.py",
  "pre_verify_cmd": "{py} {project_dir}/verify.py --pre",
  "time": "2025-02-10T11:26:33.969758"
}
    """
    manifest = Manifest.model_validate_json(json)
    assert manifest.target_dir == "/path/to/target/repo"
    assert len(manifest.files) == 1
    assert manifest.files[0].filename == "src/main/java/com/example/App.java"
