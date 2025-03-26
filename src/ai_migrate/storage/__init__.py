from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Union, BinaryIO

from .config import StorageConfig


class StorageBackend(ABC):
    """Abstract base class defining the interface for storage backends."""

    @abstractmethod
    def __init__(self, config: StorageConfig):
        """Initialize the storage backend with configuration.

        @param config Storage configuration
        @throws StorageError If the configuration is invalid or incompatible
        """
        pass

    @abstractmethod
    def save_file(
        self, source_path: Union[str, Path], destination_path: Union[str, Path]
    ) -> str:
        """Save a file to the storage backend.

        @param source_path Path to the local file to save
        @param destination_path Path/key where the file should be stored
        @return The full path/identifier where the file was stored
        @throws StorageError If the file cannot be saved
        """
        pass

    @abstractmethod
    def save_content(
        self, content: Union[str, bytes], destination_path: Union[str, Path]
    ) -> str:
        """Save raw content to the storage backend.

        @param content The content to save (string or bytes)
        @param destination_path Path/key where the content should be stored
        @return The full path/identifier where the content was stored
        @throws StorageError If the content cannot be saved
        """
        pass

    @abstractmethod
    def list_files(self, prefix: Union[str, Path] = "") -> List[str]:
        """List files in the storage backend.

        @param prefix Optional prefix to filter results (default: "")
        @return List of file paths/identifiers
        @throws StorageError If the files cannot be listed
        """
        pass

    @abstractmethod
    def get_file(self, path: Union[str, Path]) -> BinaryIO:
        """Retrieve a file from the storage backend.

        @param path Path/identifier of the file to retrieve
        @return File-like object containing the file data
        @throws StorageError If the file cannot be retrieved
        @throws FileNotFoundError If the file does not exist
        """
        pass

    @abstractmethod
    def delete_file(self, path: Union[str, Path]) -> bool:
        """Delete a file from the storage backend.

        @param path Path/identifier of the file to delete
        @return True if the file was deleted, False otherwise
        @throws StorageError If the file cannot be deleted
        """
        pass


class StorageError(Exception):
    """Base exception class for storage backend errors."""

    pass
