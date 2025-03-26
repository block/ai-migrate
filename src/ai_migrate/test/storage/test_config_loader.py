import yaml
import pytest

from ai_migrate.storage.config import StorageType
from ai_migrate.storage.config_loader import (
    load_config, find_project_root,
    create_default_config, DEFAULT_CONFIG_NAME, DEFAULT_CONFIG_CONTENT,
    PROJECT_MARKERS, find_config_file
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

def test_find_project_root_markers(tmp_path):
    # Create test directories
    project_root = tmp_path / "project"
    project_root.mkdir()
    nested_dir = project_root / "src" / "module"
    nested_dir.mkdir(parents=True)
    
    # No markers - should return None
    assert find_project_root(nested_dir) is None
    
    # Test each marker file
    for marker in PROJECT_MARKERS:
        # Clean up previous marker
        for f in project_root.glob(".*"):
            f.unlink()
        for f in project_root.glob("*.*"):
            f.unlink()
            
        # Create new marker
        (project_root / marker).touch()
        assert find_project_root(nested_dir) == project_root

def test_find_config_file(tmp_path):
    # No config files
    assert find_config_file(tmp_path) is None
    
    # Create config file
    config_path = tmp_path / DEFAULT_CONFIG_NAME
    config_path.touch()
    assert find_config_file(tmp_path) == config_path

def test_create_default_config(tmp_path):
    config_path = create_default_config(tmp_path)
    
    # Should create YAML file
    assert config_path.suffix == ".yml"
    assert config_path.exists()
    
    # Should create root marker
    assert (tmp_path / ".ai-migrate-root").exists()
    
    # Content should match default
    with open(config_path) as f:
        config = yaml.safe_load(f)
        assert config == DEFAULT_CONFIG_CONTENT

def test_project_config_override(tmp_path):
    # Create project structure
    project_root = tmp_path / "project"
    project_root.mkdir()
    nested_dir = project_root / "src" / "module"
    nested_dir.mkdir(parents=True)
    
    # Create root marker and config
    (project_root / ".ai-migrate-root").touch()
    root_config = {
        "type": "local",
        "path": "root_migrations"
    }
    with open(project_root / DEFAULT_CONFIG_NAME, 'w') as f:
        yaml.safe_dump(root_config, f)
    
    # Create project-specific config
    project_config = {
        "path": "project_migrations"
    }
    with open(nested_dir / DEFAULT_CONFIG_NAME, 'w') as f:
        yaml.safe_dump(project_config, f)
    
    # Load from project directory
    config = load_config(nested_dir)
    assert config.type == StorageType.LOCAL  # From root config
    assert str(config.path) == "project_migrations"  # Overridden

def test_env_var_override(tmp_path, monkeypatch):
    # Create project with root marker
    (tmp_path / ".ai-migrate-root").touch()
    
    # Create config
    root_config = {
        "type": "local",
        "path": "root_migrations"
    }
    with open(tmp_path / f"{DEFAULT_CONFIG_NAME}.yml", 'w') as f:
        yaml.safe_dump(root_config, f)
    
    # Set environment variables
    monkeypatch.setenv("AI_MIGRATE_STORAGE_TYPE", "s3")
    monkeypatch.setenv("AI_MIGRATE_STORAGE_BUCKET", "my-bucket")
    
    config = load_config(tmp_path)
    assert config.type == StorageType.S3  # From env
    assert config.bucket == "my-bucket"  # From env

def test_default_config_creation(tmp_path):
    # Create project with root marker
    (tmp_path / ".ai-migrate-root").touch()
    
    # First load should create default config
    config = load_config(tmp_path)
    assert config.type == StorageType.LOCAL
    assert str(config.path) == "migrations"
    
    # Config file should exist
    config_path = tmp_path / DEFAULT_CONFIG_NAME
    assert config_path.exists()
    
    # Content should match default
    with open(config_path) as f:
        config = yaml.safe_load(f)
        assert config == DEFAULT_CONFIG_CONTENT

def test_load_outside_project(tmp_path):
    # Loading outside a project should use built-in defaults
    config = load_config(tmp_path)
    assert config.type == StorageType.LOCAL
    assert str(config.path) == "migrations"