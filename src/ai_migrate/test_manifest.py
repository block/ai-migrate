from ai_migrate.manifest import Manifest, FileGroup, FileEntry


def test_valid_manifest():
    json = """
{
  "target_repo_ref": "",
  "migrate_repo_ref": "",
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
  "target_repo_ref": "",
  "migrate_repo_ref": "",
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
    }
  ],
  "system_prompt": "{project_dir}/system_prompt.md",
  "verify_cmd": "{py} {project_dir}/verify.py",
  "pre_verify_cmd": "{py} {project_dir}/verify.py --pre",
  "time": "2025-02-10T11:26:33.969758"
}
    """
    manifest = Manifest.model_validate_json(json)
    assert isinstance(manifest.files[0], FileGroup)
    assert isinstance(manifest.files[1], FileEntry)
