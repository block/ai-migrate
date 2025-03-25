import os
import yaml
import json
from pathlib import Path
from typing import Optional, Dict, Union

from .config import MigrationResultConfig, StorageConfig, StorageType

DEFAULT_CONFIG_NAME = ".ai-migrate"
DEFAULT_CONFIG_CONTENT = {
    "storage": {
        "type": "local",
        "path": "migrations"
    },
    "compress_artifacts": True,
    "store_failures": True
}

def find_project_root(start_path: Union[str, Path] = None) -> Optional[Path]:
    """Find the project root by looking for .git directory.
    
    @param start_path Starting path for the search (default: current directory)
    @return Path to project root or None if not found
    """
    current = Path(start_path or os.getcwd()).resolve()
    
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    
    return None

def create_default_config(path: Path) -> None:
    """Create default configuration file.
    
    @param path Path where to create the config file
    """
    # Try YAML first, fall back to JSON
    for ext in [".yml", ".yaml", ".json"]:
        if not (path / f"{DEFAULT_CONFIG_NAME}{ext}").exists():
            config_path = path / f"{DEFAULT_CONFIG_NAME}{ext}"
            with open(config_path, 'w') as f:
                if ext in [".yml", ".yaml"]:
                    yaml.safe_dump(DEFAULT_CONFIG_CONTENT, f, default_flow_style=False)
                else:
                    json.dump(DEFAULT_CONFIG_CONTENT, f, indent=2)
            return

def load_config_file(path: Union[str, Path]) -> Dict[str, Union[Dict, bool]]:
    """Load configuration from a file.
    
    @param path Path to configuration file (YAML or JSON)
    @return Configuration dictionary
    @throws ValueError if file format is not supported
    """
    path = Path(path).expanduser()
    if not path.exists():
        return {}

    if path.suffix not in ['.yml', '.yaml', '.json']:
        raise ValueError(f"Unsupported config file format: {path.suffix}")

    with open(path) as f:
        if path.suffix in ['.yml', '.yaml']:
            return yaml.safe_load(f) or {}
        else:
            return json.load(f) or {}

def get_env_config() -> Dict[str, Union[Dict, bool]]:
    """Get configuration from environment variables.
    
    Environment variables take the form:
    AI_MIGRATE_STORAGE_TYPE=local
    AI_MIGRATE_STORAGE_PATH=/path/to/storage
    etc.
    
    @return Configuration dictionary from environment variables
    """
    config = {}
    storage_config = {}
    
    if storage_type := os.getenv("AI_MIGRATE_STORAGE_TYPE"):
        storage_config["type"] = storage_type
    
    if storage_path := os.getenv("AI_MIGRATE_STORAGE_PATH"):
        storage_config["path"] = storage_path
    
    if auth_file := os.getenv("AI_MIGRATE_STORAGE_AUTH_FILE"):
        storage_config["auth_file"] = auth_file
    
    if bucket := os.getenv("AI_MIGRATE_STORAGE_BUCKET"):
        storage_config["bucket"] = bucket
    
    if prefix := os.getenv("AI_MIGRATE_STORAGE_PREFIX"):
        storage_config["prefix"] = prefix

    if storage_config:
        config["storage"] = storage_config

    if compress := os.getenv("AI_MIGRATE_COMPRESS_ARTIFACTS"):
        config["compress_artifacts"] = compress.lower() in ('true', '1', 'yes')
    
    if store_failures := os.getenv("AI_MIGRATE_STORE_FAILURES"):
        config["store_failures"] = store_failures.lower() in ('true', '1', 'yes')
    
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

def load_config(project_path: Optional[Union[str, Path]] = None) -> MigrationResultConfig:
    """Load configuration from files and environment.
    
    Priority (highest to lowest):
    1. Environment variables
    2. Project-specific config (if in a project directory)
    3. Default config from project root
    4. Built-in defaults
    
    @param project_path Optional path within project (default: current directory)
    @return MigrationResultConfig instance
    """
    config = DEFAULT_CONFIG_CONTENT.copy()
    
    # Find project root and load default config
    project_root = find_project_root(project_path)
    if project_root:
        # Try to load default config from project root
        for ext in ['.yml', '.yaml', '.json']:
            try:
                root_config_path = project_root / f"{DEFAULT_CONFIG_NAME}{ext}"
                if root_config_path.exists():
                    if root_config := load_config_file(root_config_path):
                        config = deep_merge(config, root_config)
                        break
            except (OSError, ValueError):
                continue
            
        # If no config exists, create default
        if all(not (project_root / f"{DEFAULT_CONFIG_NAME}{ext}").exists() 
               for ext in ['.yml', '.yaml', '.json']):
            create_default_config(project_root)
        
        # If project_path is provided and different from root, look for project-specific config
        if project_path:
            project_dir = Path(project_path)
            if project_dir != project_root:
                for ext in ['.yml', '.yaml', '.json']:
                    try:
                        if project_config := load_config_file(project_dir / f"{DEFAULT_CONFIG_NAME}{ext}"):
                            config = deep_merge(config, project_config)
                            break
                    except (OSError, ValueError):
                        continue
    
    # Override with environment variables
    env_config = get_env_config()
    config = deep_merge(config, env_config)
    
    return MigrationResultConfig.model_validate(config)