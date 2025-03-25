from pathlib import Path

import pytest

from ai_migrate.migrate import (
    FileContent,
    migrate_prompt,
    extract_code_blocks,
    CodeResponseResult,
    CodeBlock,
    MigrationExample,
    read_file_pairs_from,
)


@pytest.fixture
def examples_dir():
    return Path(__file__).parent / "test" / "examples"


def test_read_file_pairs_from(examples_dir):
    # Convert iterator to list for testing
    examples = list(read_file_pairs_from(examples_dir))

    # Sort examples by name for consistent testing
    examples.sort(key=lambda x: x.name if x.name else "")

    # We expect 2 examples: one directory pair and one file pair
    assert len(examples) == 2

    # Test directory pair example
    dir_example = examples[0]
    assert dir_example.name == "example1"

    # Sort files by name for consistent testing
    dir_example.old_files.sort(key=lambda x: x.name)
    dir_example.new_files.sort(key=lambda x: x.name)

    # Check old files
    assert len(dir_example.old_files) == 2
    assert dir_example.old_files[0].name == "src/file1.py"
    assert dir_example.old_files[1].name == "src/file2.py"
    assert (
        dir_example.old_files[0].content
        == """def old_function():
    print("This is the old version of file1")\n"""
    )
    assert (
        dir_example.old_files[1].content
        == """class OldClass:
    def method(self):
        return "old implementation"\n"""
    )

    # Check new files
    assert len(dir_example.new_files) == 2
    assert dir_example.new_files[0].name == "src/file1.py"
    assert dir_example.new_files[1].name == "src/file2.py"
    assert (
        dir_example.new_files[0].content
        == """def new_function():
    print("This is the new version of file1")\n"""
    )
    assert (
        dir_example.new_files[1].content
        == """class NewClass:
    def method(self):
        return "new implementation"\n"""
    )

    # Test single file pair example
    file_example = examples[1]
    assert file_example.name == "single"

    # Check old file
    assert len(file_example.old_files) == 1
    assert file_example.old_files[0].name == "single.py"
    assert (
        file_example.old_files[0].content
        == """def standalone_old():
    return "old standalone function"\n"""
    )

    # Check new file
    assert len(file_example.new_files) == 1
    assert file_example.new_files[0].name == "single.py"
    assert (
        file_example.new_files[0].content
        == """def standalone_new():
    return "new standalone function"\n"""
    )


def test_examples_prompt():
    example = MigrationExample(
        name="main",
        old_files=[
            FileContent(
                name="main.kt",
                content="""
fun main() {
    apiv1("Hello, world!")
}
""",
            )
        ],
        new_files=[
            FileContent(
                name="main.kt",
                content="""
fun main() {
    apiv2("Hello, world!")
}
""",
            )
        ],
    )
    messages = migrate_prompt(example)
    assert messages == [
        {
            "role": "user",
            "content": """Migrate this code to the new format:

### `main.kt`
```kotlin
fun main() {
    apiv1("Hello, world!")
}
```. Return the full content for all files mentioned, don't leave anything out. You can rename a file if necessary.""",
        },
        {
            "role": "assistant",
            "content": """Here's the migrated code:
### `main.kt`
```kotlin
fun main() {
    apiv2("Hello, world!")
}
```""",
        },
    ]


def test_no_new_code_prompt():
    example = MigrationExample(
        name="main",
        old_files=[
            FileContent(
                name="main.kt",
                content="""
fun main() {
    apiv1("Hello, world!")
}
""",
            )
        ],
        new_files=[],
    )
    messages = migrate_prompt(example)
    assert messages == [
        {
            "role": "user",
            "content": """Migrate this code to the new format:

### `main.kt`
```kotlin
fun main() {
    apiv1("Hello, world!")
}
```. Return the full content for all files mentioned, don't leave anything out. You can rename a file if necessary.""",
        }
    ]


def test_multifile_prompt():
    example = MigrationExample(
        name="multifile",
        old_files=[
            FileContent(
                name="main.kt",
                content="""
fun main() {
    hello("Hello, world!")
}
""",
            ),
            FileContent(
                name="hello.kt",
                content="""
fun hello(message: String) {
    println(message)
}
""",
            ),
        ],
        new_files=[
            FileContent(
                name="main.kt",
                content="""
fun main() {
    hello("Hello, world!", "again!")
}
""",
            ),
            FileContent(
                name="hello.kt",
                content="""
fun hello(message: String, message2: String) {
    println(message)
    println(message2)
}
""",
            ),
        ],
    )
    messages = migrate_prompt(example)
    assert messages == [
        {
            "role": "user",
            "content": """Migrate this code to the new format:

### `main.kt`
```kotlin
fun main() {
    hello("Hello, world!")
}
```

### `hello.kt`
```kotlin
fun hello(message: String) {
    println(message)
}
```. Return the full content for all files mentioned, don't leave anything out. You can rename a file if necessary.""",
        },
        {
            "role": "assistant",
            "content": """Here's the migrated code:
### `main.kt`
```kotlin
fun main() {
    hello("Hello, world!", "again!")
}
```

### `hello.kt`
```kotlin
fun hello(message: String, message2: String) {
    println(message)
    println(message2)
}
```""",
        },
    ]


def test_split_code_blocks():
    markdown = """Here's some code:
### `file1.py`
```python
def hello():
    pass
```
try it out. Some more:
```
uv run file1.py
```
"""
    result = extract_code_blocks(markdown)
    assert result == CodeResponseResult(
        code_blocks=[
            CodeBlock(filename="file1.py", code="def hello():\n    pass"),
            CodeBlock(filename=None, code="uv run file1.py"),
        ],
        other_text="Here's some code:\n<code>\ntry it out. Some more:\n<code>",
    )
