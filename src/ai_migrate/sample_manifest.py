import random

import fire

from ai_migrate.manifest import Manifest


def main(manifest_file: str, result: str, n: int) -> None:
    """Create a new manifest by sampling an existing one."""
    manifest = Manifest.model_validate_json(open(manifest_file).read())

    manifest.files = random.sample([f for f in manifest.files if f.result == result], n)
    print(manifest.model_dump_json(indent=2, exclude_defaults=True))


if __name__ == "__main__":
    fire.Fire(main)
