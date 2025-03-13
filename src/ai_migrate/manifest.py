from datetime import datetime
from hashlib import sha256

from pydantic import BaseModel, Field

SYSTEM_PROMPT_FILE = "system_prompt.md"
VERIFY_SCRIPT_FILE = "verify.py"


def flatten(filename):
    return filename.replace("/", "__")


class FileEntry(BaseModel):
    filename: str
    result: str = "?"

    def group_name(self) -> str:
        return flatten(self.filename)


class FileGroup(BaseModel):
    files: list[str]
    result: str = "?"

    def group_name(self) -> str:
        if len(self.files) == 1:
            return FileEntry(filename=self.files[0]).group_name()
        hsh = sha256(",".join(sorted(self.files)).encode()).hexdigest()[:8]
        return f"{flatten(self.files[0])}-{hsh}"


class Manifest(BaseModel):
    target_repo_ref: str = ""
    target_repo_remote: str = ""
    migrate_repo_ref: str = ""
    # noinspection PyDataclass
    files: list[FileGroup | FileEntry] = []
    system_prompt: str = f"{{project_dir}}/{SYSTEM_PROMPT_FILE}"
    verify_cmd: str = f"{{py}} {{project_dir}}/{VERIFY_SCRIPT_FILE}"
    pre_verify_cmd: str = f"{{py}} {{project_dir}}/{VERIFY_SCRIPT_FILE} --pre"
    time: datetime = Field(default_factory=datetime.now)
