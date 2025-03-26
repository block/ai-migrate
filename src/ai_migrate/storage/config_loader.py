import os
import yaml
from pathlib import Path
from typing import Optional, Dict, Union

from .config import StorageConfig

DEFAULT_CONFIG_NAME = ".ai-migrate.yml"
PROJECT_MARKERS = [
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    ".ai-migrate-root",
    DEFAULT_CONFIG_NAME,
]

DEFAULT_CONFIG_CONTENT = {
    "type": "local",
    "path": "migrations"
}

def find_project_root(start_path: Union[str, Path] = None) -> Optional[Path]:
    """Find the project root by looking for project marker files.
    
    @param start_path Starting path for the search (default: current directory)
    @return Path to project root or None if not found
    """
    current = Path(start_path or os.getcwd()).resolve()
    
    while current != current.parent:
        # Check for any of the marker files
        for marker in PROJECT_MARKERS:
            if (current / marker).exists():
                return current
        current = current.parent
    
    return None

def find_config_file(directory: Path) -> Optional[Path]:
    """Find configuration file in the given directory.
    
    @param directory Directory to search in
    @return Path to config file or None if not found
    """
    config_path = directory / DEFAULT_CONFIG_NAME
    return config_path if config_path.exists() else None

def create_default_config(path: Path) -> Path:
    """Create default configuration file.
    
    @param path Path where to create the config file
    @return Path to created config file
    """
    config_path = path / DEFAULT_CONFIG_NAME
    with open(config_path, 'w') as f:
        yaml.safe_dump(DEFAULT_CONFIG_CONTENT, f, default_flow_style=False)
    
    # Also create root marker if it doesn't exist
    root_marker = path / ".ai-migrate-root"
    if not root_marker.exists():
        root_marker.touch()
    
    return config_path

def load_config_file(path: Union[str, Path]) -> Dict[str, Union[Dict, str]]:
    """Load configuration from a file.
    
    @param path Path to configuration file
    @return Configuration dictionary
    @throws ValueError if file cannot be loaded
    """
    path = Path(path).expanduser()
    if not path.exists():
        return {}

    if path.suffix != '.yml':
        raise ValueError("Config file must be YAML (.yml)")

    with open(path) as f:
        return yaml.safe_load(f) or {}

def get_env_config() -> Dict[str, Union[Dict, str]]:
    """Get configuration from environment variables.
    
    Environment variables take the form:
    AI_MIGRATE_STORAGE_TYPE=local
    AI_MIGRATE_STORAGE_PATH=/path/to/storage
    etc.
    
    @return Configuration dictionary from environment variables
    """
    config = {}
    
    if storage_type := os.getenv("AI_MIGRATE_STORAGE_TYPE"):
        config["type"] = storage_type
    
    if storage_path := os.getenv("AI_MIGRATE_STORAGE_PATH"):
        config["path"] = storage_path
    
    if auth_file := os.getenv("AI_MIGRATE_STORAGE_AUTH_FILE"):
        config["auth_file"] = auth_file
    
    if bucket := os.getenv("AI_MIGRATE_STORAGE_BUCKET"):
        config["bucket"] = bucket
    
    if prefix := os.getenv("AI_MIGRATE_STORAGE_PREFIX"):
        config["prefix"] = prefix
    
    return config

def deep_merge(base: Dict, override: Dict) -> Dict:
    """Deep merge two dictionaries.
    
    @param base Base dictionary
    @param override Dictionary with overrides
    @return Merged dictionary
    """
    result = base.copy()
    for key, value in override.items():
        if (
            key in result and 
            isinstance(result[key], dict) and 
            isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result

def load_config(project_path: Optional[Union[str, Path]] = None) -> StorageConfig:
    """Load configuration from files and environment.
    
    Priority (highest to lowest):
    1. Environment variables
    2. Project-specific config (if in a project directory)
    3. Default config from project root
    4. Built-in defaults
    
    @param project_path Optional path within project (default: current directory)
    @return StorageConfig instance
    """
    config = DEFAULT_CONFIG_CONTENT.copy()
    
    # Find project root and load default config
    project_root = find_project_root(project_path)
    if project_root:
        # Try to load default config from project root
        if root_config_path := find_config_file(project_root):
            try:
                if root_config := load_config_file(root_config_path):
                    config = deep_merge(config, root_config)
            except (OSError, ValueError):
                pass
        else:
            # Create default config if none exists
            root_config_path = create_default_config(project_root)
            try:
                if root_config := load_config_file(root_config_path):
                    config = deep_merge(config, root_config)
            except (OSError, ValueError):
                pass
        
        # If project_path is provided and different from root, look for project-specific config
        if project_path:
            project_dir = Path(project_path)
            if project_dir != project_root:
                if project_config_path := find_config_file(project_dir):
                    try:
                        if project_config := load_config_file(project_config_path):
                            config = deep_merge(config, project_config)
                    except (OSError, ValueError):
                        pass
    
    # Override with environment variables
    env_config = get_env_config()
    config = deep_merge(config, env_config)
    
    return StorageConfig.model_validate(config)