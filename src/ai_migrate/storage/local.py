import os
import shutil
from pathlib import Path
from typing import List, Union, BinaryIO

from . import StorageBackend, StorageError
from .config import StorageConfig, StorageType

class LocalStorageBackend(StorageBackend):
    """Storage backend implementation using the local filesystem."""
    
    def __init__(self, config: StorageConfig):
        """Initialize the local storage backend.
        
        @param config Storage configuration
        @throws StorageError If the configuration is invalid or incompatible
        """
        if config.type != StorageType.LOCAL:
            raise StorageError(f"Invalid storage type {config.type} for LocalStorageBackend")

        self.base_path = Path(config.path or Path.cwd())
        try:
            self.base_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise StorageError(f"Invalid base_path configuration: {e}") from e
        
    def save_file(self, source_path: Union[str, Path], destination_path: Union[str, Path]) -> str:
        """Save a file to the local filesystem.
        
        @param source_path Path to the source file
        @param destination_path Relative path where the file should be stored
        @return The full path where the file was stored
        @throws StorageError If the file cannot be saved
        """
        try:
            source_path = Path(source_path)
            dest_path = self.base_path / destination_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, dest_path)
            return str(dest_path)
        except (OSError, shutil.Error) as e:
            raise StorageError(f"Failed to save file: {e}") from e
    
    def save_content(self, content: Union[str, bytes], destination_path: Union[str, Path]) -> str:
        """Save content to a file in the local filesystem.
        
        @param content The content to save
        @param destination_path Relative path where the content should be stored
        @return The full path where the content was stored
        @throws StorageError If the content cannot be saved
        """
        try:
            dest_path = self.base_path / destination_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            mode = 'wb' if isinstance(content, bytes) else 'w'
            with open(dest_path, mode) as f:
                f.write(content)
            return str(dest_path)
        except OSError as e:
            raise StorageError(f"Failed to save content: {e}") from e
    
    def list_files(self, prefix: Union[str, Path] = "") -> List[str]:
        """List files in the local filesystem.
        
        @param prefix Optional path prefix to filter results (default: "")
        @return List of file paths relative to base_path
        @throws StorageError If the files cannot be listed
        """
        try:
            search_path = self.base_path / prefix
            if not search_path.exists():
                return []
                
            result = []
            for root, _, files in os.walk(search_path):
                root_path = Path(root)
                for file in files:
                    full_path = root_path / file
                    relative_path = str(full_path.relative_to(self.base_path))
                    result.append(relative_path)
            
            return sorted(result)
        except OSError as e:
            raise StorageError(f"Failed to list files: {e}") from e
    
    def get_file(self, path: Union[str, Path]) -> BinaryIO:
        """Retrieve a file from the local filesystem.
        
        @param path Path to the file relative to base_path
        @return Open file handle in binary read mode
        @throws StorageError If the file cannot be opened
        @throws FileNotFoundError If the file does not exist
        """
        file_path = self.base_path / path
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        
        try:
            return open(file_path, 'rb')
        except OSError as e:
            raise StorageError(f"Failed to open file: {e}") from e
    
    def delete_file(self, path: Union[str, Path]) -> bool:
        """Delete a file from the local filesystem.
        
        @param path Path to the file relative to base_path
        @return True if the file was deleted, False if it didn't exist
        @throws StorageError If the file exists but cannot be deleted
        """
        try:
            file_path = self.base_path / path
            if not file_path.exists():
                return False
            
            file_path.unlink()
            return True
        except OSError as e:
            raise StorageError(f"Failed to delete file: {e}") from e