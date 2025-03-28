from datetime import datetime
from pathlib import Path
import boto3
import asyncio
import shutil
import logging

logger = logging.getLogger("ai_migrate.s3_uploader")


class S3Uploader:
    def __init__(self, bucket_name: str):
        self.s3_client = boto3.client("s3") if bucket_name != "localhost" else None
        self.bucket = bucket_name

    async def upload(
        self, project: str, paths: list[Path], result_type: str, timestamp: datetime
    ) -> None:
        dest = Path(f"{project}/attempt-{timestamp.strftime('%Y%m%d-%H%M%S')}")
        if result_type:
            dest = dest / result_type

        if self.bucket == "localhost":
            dest = Path("~/ai-migration-results").expanduser() / dest
            dest.mkdir(parents=True, exist_ok=True)
            for path in paths:
                try:
                    shutil.copy2(path, dest / path.name)
                except OSError as e:
                    logger.error(f"Failed to save {path.name}: {e}")
            return

        semaphore = asyncio.Semaphore(5)

        async def upload_one(path: Path):
            key = str(dest / path.name)
            try:
                async with semaphore:
                    await asyncio.to_thread(
                        self.s3_client.put_object,
                        Bucket=self.bucket,
                        Key=key,
                        Body=path.read_bytes(),
                    )
            except Exception as e:
                logger.error(f"Failed to upload {path.name} to {self.bucket}: {e}")

        await asyncio.gather(*[upload_one(path) for path in paths])

    async def upload_results(
        self,
        project: str,
        results: list,
        results_file: Path,
        timestamp: datetime = None,
    ) -> None:
        timestamp = timestamp or datetime.now()
        await self.upload(project, [results_file], "manifest", timestamp)
        for result in results:
            await self.upload(
                project, [Path(f) for f in result.files], result.result, timestamp
            )
