"""Test suite for ai-migrate storage backends."""

import os
import pytest
from pathlib import Path
from typing import BinaryIO

from ai_migrate.storage import StorageBackend, StorageError
from ai_migrate.storage.local import LocalStorageBackend

@pytest.fixture
def temp_storage_dir(tmp_path):
    """@return Temporary directory for storage tests."""
    return tmp_path

@pytest.fixture
def local_backend(temp_storage_dir):
    """@return LocalStorageBackend instance for testing."""
    return LocalStorageBackend(base_path=temp_storage_dir)

def test_save_and_retrieve_file(local_backend, temp_storage_dir):
    """Test saving and retrieving a file."""
    test_file = temp_storage_dir / "test_input.txt"
    test_content = b"Hello, World!"
    test_file.write_bytes(test_content)
    
    saved_path = local_backend.save_file(test_file, "output/test.txt")
    assert Path(saved_path).exists()
    
    with local_backend.get_file("output/test.txt") as f:
        content = f.read()
        assert content == test_content

def test_save_and_retrieve_content(local_backend):
    """Test saving and retrieving raw content."""
    str_content = "Hello, World!"
    str_path = local_backend.save_content(str_content, "test_str.txt")
    assert Path(str_path).exists()
    
    with open(str_path, 'r') as f:
        assert f.read() == str_content
    
    bin_content = b"Binary Data"
    bin_path = local_backend.save_content(bin_content, "test_bin.dat")
    assert Path(bin_path).exists()
    
    with open(bin_path, 'rb') as f:
        assert f.read() == bin_content

def test_list_files(local_backend):
    """Test listing files in the storage."""
    local_backend.save_content("test1", "a/test1.txt")
    local_backend.save_content("test2", "a/b/test2.txt")
    local_backend.save_content("test3", "c/test3.txt")
    
    files = local_backend.list_files()
    assert len(files) == 3
    assert "a/test1.txt" in files
    assert "a/b/test2.txt" in files
    assert "c/test3.txt" in files
    
    files = local_backend.list_files("a")
    assert len(files) == 2
    assert "a/test1.txt" in files
    assert "a/b/test2.txt" in files

def test_delete_file(local_backend):
    """Test deleting files."""
    path = local_backend.save_content("test", "delete_me.txt")
    assert Path(path).exists()
    
    assert local_backend.delete_file("delete_me.txt") == True
    assert not Path(path).exists()
    
    assert local_backend.delete_file("nonexistent.txt") == False

def test_configure(local_backend, tmp_path):
    """Test backend configuration."""
    new_base = tmp_path / "new_base"
    
    local_backend.configure({"base_path": str(new_base)})
    assert local_backend.base_path == new_base
    assert new_base.exists()
    
    local_backend.save_content("test", "test.txt")
    assert (new_base / "test.txt").exists()

def test_error_handling(local_backend):
    """Test error handling in various scenarios."""
    with pytest.raises(StorageError):
        local_backend.save_file("nonexistent.txt", "test.txt")
    
    with pytest.raises(FileNotFoundError):
        local_backend.get_file("nonexistent.txt")
    
    test_file = local_backend.save_content("test", "test.txt")
    with pytest.raises(StorageError):
        local_backend.configure({"base_path": test_file})