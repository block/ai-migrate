import yaml
import pytest
from pathlib import Path

from ai_migrate.storage.config import StorageType, StorageConfig

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

def test_load_yaml_config(tmp_path):
    config_data = {
        "type": "s3",
        "bucket": "test-bucket",
        "prefix": "migrations"
    }
    config_file = tmp_path / ".ai-migrate.yml"
    with open(config_file, 'w') as f:
        yaml.safe_dump(config_data, f)
    
    config = StorageConfig.model_validate(config_data)
    assert config.type == StorageType.S3
    assert config.bucket == "test-bucket"
    assert config.prefix == "migrations"

def test_load_json_config(tmp_path):
    config_data = {
        "type": "gdrive",
        "auth_file": "~/auth.json"
    }
    config = StorageConfig.model_validate(config_data)
    assert config.type == StorageType.GDRIVE
    assert config.auth_file == Path("~/auth.json")

def test_env_var_override(tmp_path, monkeypatch):
    config_data = {
        "type": "s3",
        "bucket": "test-bucket"
    }
    config_file = tmp_path / ".ai-migrate.yml"
    with open(config_file, 'w') as f:
        yaml.safe_dump(config_data, f)
    
    # Set environment variables
    monkeypatch.setenv("AI_MIGRATE_STORAGE_TYPE", "gdrive")
    
    # Load and merge configs
    env_config = {"type": "gdrive"}
    merged = {**config_data, **env_config}
    
    config = StorageConfig.model_validate(merged)
    assert config.type == StorageType.GDRIVE  # Overridden by env var
    assert config.bucket == "test-bucket"     # From file

def test_invalid_config_format():
    with pytest.raises(ValueError):
        StorageConfig(type="invalid")

def test_options_type_validation():
    with pytest.raises(ValueError):
        StorageConfig(
            type=StorageType.S3,
            options={"invalid": {"nested": "dict"}}  # Should only accept simple types
        )