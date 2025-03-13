import csv

from ai_migrate.manifest import Manifest


def main(*files: str, results_file: str = "results.csv"):
    writer = csv.writer(open(results_file, "w"))
    writer.writerow(["manifest_file", "time", "file", "result"])
    for manifest_file in files:
        print(f"Processing {manifest_file}")
        manifest = Manifest.model_validate_json(open(manifest_file).read())
        for file in manifest.files:
            writer.writerow(
                (
                    manifest_file,
                    manifest.time,
                    file.filename,
                    file.result,
                )
            )
