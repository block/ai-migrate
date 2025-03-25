import os
import yaml
import pytest
from pathlib import Path
from typing import Dict, Union

from ai_migrate.storage.config import StorageType, StorageConfig, MigrationResultConfig
from ai_migrate.storage.config_loader import (
    load_config, load_config_file, find_project_root,
    create_default_config, DEFAULT_CONFIG_NAME, DEFAULT_CONFIG_CONTENT
)

@pytest.fixture
def git_project(tmp_path):
    """Create a fake git project with nested directories."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / ".git").mkdir()
    
    # Create a nested directory structure
    nested_dir = project_root / "src" / "module"
    nested_dir.mkdir(parents=True)
    
    return project_root

def test_find_project_root(git_project):
    nested_dir = git_project / "src" / "module"
    assert find_project_root(nested_dir) == git_project
    assert find_project_root(git_project) == git_project
    assert find_project_root("/nonexistent") is None

def test_create_default_config(git_project):
    create_default_config(git_project)
    
    # Should create YAML by default
    config_file = git_project / f"{DEFAULT_CONFIG_NAME}.yml"
    assert config_file.exists()
    
    # Content should match default
    config = load_config_file(config_file)
    assert config == DEFAULT_CONFIG_CONTENT

def test_project_config_override(git_project):
    # Create default config in project root
    root_config = {
        "storage": {
            "type": "local",
            "path": "root_migrations"
        },
        "compress_artifacts": True
    }
    with open(git_project / f"{DEFAULT_CONFIG_NAME}.yml", 'w') as f:
        yaml.safe_dump(root_config, f)
    
    # Create project-specific config
    project_dir = git_project / "src" / "module"
    project_config = {
        "storage": {
            "path": "project_migrations"
        },
        "compress_artifacts": False
    }
    with open(project_dir / f"{DEFAULT_CONFIG_NAME}.yml", 'w') as f:
        yaml.safe_dump(project_config, f)
    
    # Load from project directory
    config = load_config(project_dir)
    assert config.storage.type == StorageType.LOCAL  # From root config
    assert str(config.storage.path) == "project_migrations"  # Overridden
    assert config.compress_artifacts is False  # Overridden
    assert config.store_failures is True  # From defaults

def test_env_var_override(git_project, monkeypatch):
    # Create default config
    root_config = {
        "storage": {
            "type": "local",
            "path": "root_migrations"
        }
    }
    with open(git_project / f"{DEFAULT_CONFIG_NAME}.yml", 'w') as f:
        yaml.safe_dump(root_config, f)
    
    # Set environment variables
    monkeypatch.setenv("AI_MIGRATE_STORAGE_TYPE", "s3")
    monkeypatch.setenv("AI_MIGRATE_STORAGE_BUCKET", "my-bucket")
    
    config = load_config(git_project)
    assert config.storage.type == StorageType.S3  # From env
    assert config.storage.bucket == "my-bucket"  # From env

def test_default_config_creation(git_project):
    # First load should create default config
    config = load_config(git_project)
    assert config.storage.type == StorageType.LOCAL
    assert str(config.storage.path) == "migrations"
    
    # Config file should exist
    assert any(
        (git_project / f"{DEFAULT_CONFIG_NAME}{ext}").exists()
        for ext in [".yml", ".yaml", ".json"]
    )

def test_load_outside_project(tmp_path):
    # Loading outside a project should use built-in defaults
    config = load_config(tmp_path)
    assert config.storage.type == StorageType.LOCAL
    assert str(config.storage.path) == "migrations"
    assert config.compress_artifacts is True
    assert config.store_failures is True