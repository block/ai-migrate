from datetime import datetime
from pathlib import Path
import boto3
import logging
from .manifest import FileGroup

logger = logging.getLogger("ai_migrate.s3_uploader")


class S3Uploader:
    def __init__(self, bucket_name: str):
        self.s3_client = boto3.client("s3")
        self.bucket = bucket_name

    def upload(self, project: str, file_path: Path, result_type: str) -> str:
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        base_key = f"{project}/attempt-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        key = f"{base_key}/{'logs' if result_type == 'log' else result_type}/{str(file_path).lstrip('./')}"

        try:
            self.s3_client.put_object(
                Bucket=self.bucket, Key=key, Body=file_path.read_bytes()
            )
            url = f"s3://{self.bucket}/{key}"
            logger.info(f"Uploaded to {url}")
            return url
        except Exception as e:
            logger.error(f"Failed to upload {file_path} to {url}: {e}")
            raise

    def upload_migration(
        self, project: str, file_group: FileGroup, log_file: str | Path
    ) -> None:
        self.upload(project, log_file, "log")
        for file in (f for f in file_group.files if Path(f).exists()):
            self.upload(project, Path(file), file_group.result)
