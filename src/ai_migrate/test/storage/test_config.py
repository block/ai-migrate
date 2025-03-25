import os
import yaml
import pytest
from pathlib import Path
from typing import Dict, Union

from ai_migrate.storage.config import StorageType, StorageConfig, MigrationResultConfig
from ai_migrate.storage.config_loader import (
    load_config, load_config_file, DEFAULT_CONFIG_NAME
)

@pytest.fixture
def temp_project_dir(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".git").mkdir()
    return project_dir

def test_storage_config_defaults():
    config = StorageConfig()
    assert config.type == StorageType.LOCAL
    assert config.path is None
    assert config.auth_file is None
    assert config.bucket is None
    assert config.prefix is None
    assert config.options == {}

def test_storage_config_validation():
    config = StorageConfig(path="/tmp/test")
    assert isinstance(config.path, Path)
    assert str(config.path) == "/tmp/test"

def test_migration_result_config_defaults():
    config = MigrationResultConfig()
    assert config.storage.type == StorageType.LOCAL
    assert config.compress_artifacts is True
    assert config.store_failures is True

def test_load_yaml_config(temp_project_dir):
    config_data = """
    storage:
      type: s3
      bucket: test-bucket
      prefix: migrations
    compress_artifacts: false
    """
    config_path = temp_project_dir / f"{DEFAULT_CONFIG_NAME}.yml"
    config_path.write_text(config_data)
    
    config = load_config(temp_project_dir)
    assert config.storage.type == StorageType.S3
    assert config.storage.bucket == "test-bucket"
    assert config.storage.prefix == "migrations"
    assert config.compress_artifacts is False

def test_load_json_config(temp_project_dir):
    json_config = temp_project_dir / f"{DEFAULT_CONFIG_NAME}.json"
    json_config.write_text('{"storage": {"type": "gdrive", "auth_file": "~/auth.json"}, "store_failures": false}')
    
    config = load_config(temp_project_dir)
    assert config.storage.type == StorageType.GDRIVE
    assert config.storage.auth_file == Path("~/auth.json")
    assert config.store_failures is False

def test_env_var_override(temp_project_dir, monkeypatch):
    config_data = """
    storage:
      type: s3
      bucket: test-bucket
    store_failures: false
    """
    config_path = temp_project_dir / f"{DEFAULT_CONFIG_NAME}.yml"
    config_path.write_text(config_data)
    
    # Set environment variables
    monkeypatch.setenv("AI_MIGRATE_STORAGE_TYPE", "gdrive")
    monkeypatch.setenv("AI_MIGRATE_STORE_FAILURES", "true")
    
    config = load_config(temp_project_dir)
    assert config.storage.type == StorageType.GDRIVE  # Overridden by env var
    assert config.storage.bucket == "test-bucket"     # From file
    assert config.store_failures is True              # Overridden by env var

def test_invalid_config_file(tmp_path):
    invalid_file = tmp_path / "config.txt"
    invalid_file.touch()
    with pytest.raises(ValueError):
        load_config_file(invalid_file)

def test_get_backend_config():
    config = StorageConfig(
        type=StorageType.S3,
        bucket="test-bucket",
        prefix="migrations",
        options={"region": "us-west-2", "max_retries": 3}
    )
    
    backend_config = config.get_backend_config()
    assert "type" not in backend_config
    assert backend_config["bucket"] == "test-bucket"
    assert backend_config["prefix"] == "migrations"
    assert backend_config["region"] == "us-west-2"
    assert backend_config["max_retries"] == 3

def test_options_type_validation():
    with pytest.raises(ValueError):
        StorageConfig(
            type=StorageType.S3,
            options={"invalid": {"nested": "dict"}}  # Should only accept simple types
        )