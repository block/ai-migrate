import pytest
from pathlib import Path

from ai_migrate.storage import StorageError
from ai_migrate.storage.local import LocalStorageBackend
from ai_migrate.storage.config import StorageConfig, StorageType

@pytest.fixture
def temp_storage_dir(tmp_path):
    return tmp_path

@pytest.fixture
def local_backend(temp_storage_dir):
    config = StorageConfig(type=StorageType.LOCAL, path=temp_storage_dir)
    return LocalStorageBackend(config)

def test_save_and_retrieve_file(local_backend, temp_storage_dir):
    test_file = temp_storage_dir / "test_input.txt"
    test_content = b"Hello, World!"
    test_file.write_bytes(test_content)
    
    saved_path = local_backend.save_file(test_file, "output/test.txt")
    assert Path(saved_path).exists()
    
    with local_backend.get_file("output/test.txt") as f:
        content = f.read()
        assert content == test_content

def test_save_and_retrieve_content(local_backend):
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
    path = local_backend.save_content("test", "delete_me.txt")
    assert Path(path).exists()
    
    assert local_backend.delete_file("delete_me.txt")
    assert not Path(path).exists()
    
    assert not local_backend.delete_file("nonexistent.txt")

def test_invalid_storage_type():
    config = StorageConfig(type=StorageType.S3)
    with pytest.raises(StorageError, match="Invalid storage type"):
        LocalStorageBackend(config)

def test_storage_with_prefix(temp_storage_dir):
    config = StorageConfig(
        type=StorageType.LOCAL,
        path=temp_storage_dir,
        prefix="storage"
    )
    backend = LocalStorageBackend(config)
    
    # Verify prefix directory is created
    prefix_dir = temp_storage_dir / "storage"
    assert prefix_dir.exists()
    assert prefix_dir.is_dir()
    
    # Save and list files
    backend.save_content("test1", "a/test1.txt")
    backend.save_content("test2", "b/test2.txt")
    
    # Files should be in prefix directory
    assert (prefix_dir / "a/test1.txt").exists()
    assert (prefix_dir / "b/test2.txt").exists()
    
    # List should return paths relative to prefix
    files = backend.list_files()
    assert sorted(files) == ["a/test1.txt", "b/test2.txt"]
    
    # Get file should work with relative paths
    with backend.get_file("a/test1.txt") as f:
        assert f.read() == b"test1"

def test_invalid_base_path(tmp_path):
    invalid_path = tmp_path / "file.txt"
    invalid_path.write_text("test")
    
    config = StorageConfig(type=StorageType.LOCAL, path=str(invalid_path))
    with pytest.raises(StorageError, match="Invalid base_path"):
        LocalStorageBackend(config)

def test_invalid_prefix(temp_storage_dir):
    # Create a file where prefix should be a directory
    prefix_path = temp_storage_dir / "prefix"
    prefix_path.write_text("test")
    
    config = StorageConfig(
        type=StorageType.LOCAL,
        path=temp_storage_dir,
        prefix="prefix"
    )
    with pytest.raises(StorageError, match="Invalid prefix"):
        LocalStorageBackend(config)