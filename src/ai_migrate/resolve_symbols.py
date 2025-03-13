import json
import os
import re
import subprocess

REPOSITORY_TREE = None


def contains_definition(line: str, symbol: str) -> bool:
    line = line.strip()
    if re.match(
        rf"^(public|private|protected|static|final|abstract|synchronized|data|\s)*"
        rf"(class|interface|enum|void|[a-zA-Z_][a-zA-Z0-9_<,>\[\]]*)\s+{re.escape(symbol)}(\s*<[^>]+>)?\b",
        line,
    ):
        return True
    return bool(
        re.match(
            rf"^(public|private|protected|static|final|\s)*"
            rf"[a-zA-Z_][a-zA-Z0-9_<,>\[\]]*\s+{re.escape(symbol)}\s*\(.*\)",
            line,
        )
    )


def find_symbol_definition(file_path: str, symbol_name: str) -> str | None:
    in_comment = False
    in_definition = False
    current_comment = []
    current_definition = []
    # Hacky way to handle nested symbols:
    symbol_bits = symbol_name.split(".")

    with open(file_path, "r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue

            line = line.rstrip()
            if in_comment:
                if (p := line.find("*/")) != -1:
                    current_comment.append(line[: p + 2])
                    in_comment = False
                    continue
                else:
                    current_comment.append(line)
                    continue
            if "//" in line:
                line, comment = line.split("//", 1)
                current_comment.append(comment)

            if (p := line.find("/*")) != -1:
                endp = line.find("*/", p)
                current_comment = [line[p:] if endp == -1 else line[p : endp + 2]]
                line = line[:p]
                in_comment = endp == -1

            if symbol_bits and contains_definition(line, symbol_bits[0]):
                symbol_bits.pop(0)
                in_definition = len(symbol_bits) == 0

            if not in_definition:
                current_comment = []
                continue

            if "{" in line or ";" in line:
                line = line.split("{")[0].split(";")[0].strip()
                all_lines = [*current_comment, *current_definition, line]
                return "\n".join(all_lines)

            current_definition.append(line)
    return None


def get_symbol_definition(symbol: str, package: str) -> str | None:
    global REPOSITORY_TREE
    if REPOSITORY_TREE is None:
        REPOSITORY_TREE = scan_repository()
    root = REPOSITORY_TREE
    for bit in package.split("."):
        if bit not in root:
            break
        root = root[bit]
    for file_path in root.get("__files__", []):
        definition = find_symbol_definition(file_path, symbol)
        if definition:
            return definition
    return None


def scan_repository(root_dir: str | None = None) -> dict[str, str]:
    if root_dir is None:
        root_dir = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        ).stdout.strip()
    cache_path = os.path.join(root_dir, "symbol_tree.json")
    if os.path.exists(cache_path):
        with open(cache_path, "r") as f:
            return json.load(f)
    print("Building symbol tree for repository at", root_dir)
    symbol_tree = {}
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.endswith((".kt", ".java")):
                file_path = os.path.join(dirpath, filename)
                for line in open(file_path, "r"):
                    if line.startswith("package "):
                        package = line.split("package ", 1)[1].strip()
                        break
                else:
                    continue
                root = symbol_tree
                for bit in package.split("."):
                    root = root.setdefault(bit, {})
                root.setdefault("__files__", []).append(file_path)
    with open(cache_path, "w") as f:
        json.dump(symbol_tree, f, indent=2)
    return symbol_tree


if __name__ == "__main__":
    scan_repository()
