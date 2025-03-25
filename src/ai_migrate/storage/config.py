from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Union

from pydantic import BaseModel, Field, field_validator

class StorageType(str, Enum):
    LOCAL = "local"
    GDRIVE = "gdrive"
    S3 = "s3"
    GCS = "gcs"
    AZURE = "azure"

class StorageConfig(BaseModel):
    type: StorageType = Field(
        default=StorageType.LOCAL,
        description="Storage backend type"
    )
    path: Optional[Path] = Field(
        default=None,
        description="Base path for local storage"
    )
    auth_file: Optional[Path] = Field(
        default=None,
        description="Path to authentication file for cloud storage"
    )
    bucket: Optional[str] = Field(
        default=None,
        description="Bucket name for cloud storage"
    )
    prefix: Optional[str] = Field(
        default=None,
        description="Prefix/folder path within storage"
    )
    options: Dict[str, Union[str, int, float, bool]] = Field(
        default_factory=dict,
        description="Additional backend-specific options"
    )

    @field_validator("path")
    def validate_path(cls, v: Optional[Union[str, Path]]) -> Optional[Path]:
        if v is None:
            return None
        return Path(v)

    def get_backend_config(self) -> Dict[str, Union[Path, str, int, float, bool]]:
        """Get backend-specific configuration dictionary.

        @return Configuration dictionary for storage backend
        """
        config = self.model_dump(exclude_none=True)
        del config["type"]
        return {**config, **self.options}

class MigrationResultConfig(BaseModel):
    storage: StorageConfig = Field(
        default_factory=StorageConfig,
        description="Storage configuration for migration results"
    )
    compress_artifacts: bool = Field(
        default=True,
        description="Whether to compress migration artifacts"
    )
    store_failures: bool = Field(
        default=True,
        description="Whether to store failed migration results"
    )