from datetime import datetime
from hashlib import sha256
from pathlib import Path

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
    base_name: str = ""  # Computed from directory

    def group_name(self) -> str:
        if len(self.files) == 1:
            return FileEntry(filename=self.files[0]).group_name()
        hsh = sha256(",".join(sorted(self.files)).encode()).hexdigest()[:8]
        return f"{flatten(self.files[0])}-{hsh}"


class Directory(BaseModel):
    dir: str
    glob: str = "**/*"  # Default to all files
    result: str = "?"

    def group_name(self) -> str:
        hsh = sha256(f"{self.dir}:{self.glob}".encode()).hexdigest()[:8]
        return f"{flatten(self.dir)}-{hsh}"

    def to_file_group(self) -> FileGroup:
        """Convert this Directory to a FileGroup by recursively finding all files.

        If a glob pattern is specified, only files matching the pattern will be included.
        Supports brace expansion patterns like "**/*.{kt,js}" for multiple extensions.
        """
        files = []
        dir_path = Path(self.dir)

        if dir_path.exists() and dir_path.is_dir():
            if "{" in self.glob and "}" in self.glob:
                prefix, suffix = self.glob.split("{", 1)
                extensions = suffix.split("}", 1)[0].split(",")
                remainder = suffix.split("}", 1)[1] if "}" in suffix else ""
                patterns = [f"{prefix}{ext}{remainder}" for ext in extensions]

                for pattern in patterns:
                    for item in dir_path.glob(pattern):
                        if item.is_file():
                            files.append(str(item))
            else:
                for item in dir_path.glob(self.glob):
                    if item.is_file():
                        files.append(str(item))

        base_name = self.dir.split("/")[-1]
        return FileGroup(files=files, result=self.result, base_name=base_name)


class Manifest(BaseModel):
    eval_target_repo_ref: str = ""
    eval_target_repo_remote: str = ""
    # noinspection PyDataclass
    files: list[FileGroup | FileEntry | Directory] = []
    target_dir: str = ""
    system_prompt: str = f"{{project_dir}}/{SYSTEM_PROMPT_FILE}"
    verify_cmd: str = f"{{py}} {{project_dir}}/{VERIFY_SCRIPT_FILE}"
    pre_verify_cmd: str = f"{{py}} {{project_dir}}/{VERIFY_SCRIPT_FILE} --pre"
    time: datetime = Field(default_factory=datetime.now)
