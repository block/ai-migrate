"""Example selection logic for optimizing migration context."""

from dataclasses import dataclass
from typing import List
from pathlib import Path
from .migrate import DefaultClient, MigrationExample

EXAMPLE_SELECTION_PROMPT = """You are an expert at analyzing code migration patterns. Your task is to select the most relevant examples for migrating specific target files.

Analyze the target files and all available example pairs. Then select only the examples that demonstrate patterns and transformations that will be most helpful for migrating the target.

Consider:
1. Language features and syntax
2. Similar patterns or structures
3. Related functionality or domain
4. Migration complexity and scope

IMPORTANT: You must provide your response in the following JSON format:

{
    "analysis": "Brief analysis of what needs to be migrated in the target files",
    "selected_examples": [
        {
            "id": "Example number (integer)",
            "reason": "Detailed justification for selecting this example"
        }
    ],
    "excluded_examples": [
        {
            "id": "Example number (integer)", 
            "reason": "Brief reason for excluding this example"
        }
    ]
}

Notes:
- Example numbers should be integers (1, 2, 3, etc.)
- Provide clear, specific reasons for each selection and exclusion
- Focus on selecting examples that demonstrate patterns needed for this specific migration
- Ensure the response is valid JSON that can be parsed programmatically"""


@dataclass
class ExampleSelectionResult:
    selected_examples: List[MigrationExample]
    analysis: str
    selection_reasons: dict[str, str]
    exclusion_reasons: dict[str, str]


async def select_relevant_examples(
    target_files: List[str],
    available_examples: List[MigrationExample],
    client: DefaultClient,
) -> ExampleSelectionResult:
    target_content = []
    for target_file in target_files:
        path = Path(target_file)
        content = path.read_text()
        target_content.append(f"### `{path.name}`\n```\n{content}\n```")

    examples_content = []
    for i, example in enumerate(available_examples, 1):
        example_files = []
        for old_file in example.old_files:
            example_files.append(f"### `{old_file.name}`\n```\n{old_file.content}\n```")
            for new_file in example.new_files:
                if new_file.name == old_file.name:
                    example_files.append(
                        f"### `{new_file.name}` (migrated)\n```\n{new_file.content}\n```"
                    )
                    break
        examples_content.append(
            f"Example {i} ({example.name}):\n" + "\n".join(example_files)
        )

    prompt = (
        f"{EXAMPLE_SELECTION_PROMPT}\n\n"
        f"Target Files:\n{chr(10).join(target_content)}\n\n"
        f"Available Examples:\n\n{chr(10).join(examples_content)}"
    )

    messages = [
        {"role": "system", "content": EXAMPLE_SELECTION_PROMPT},
        {"role": "user", "content": prompt},
    ]

    response, _ = await client.generate_completion(messages=messages, temperature=0.1)
    content = response["choices"][0]["message"]["content"]
    
    import json
    try:
        result = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse LLM response as JSON: {e}\nResponse: {content}")

    # Extract analysis
    analysis = result.get("analysis", "")

    # Process selected examples
    selected_indices = []
    selection_reasons = {}
    for example in result.get("selected_examples", []):
        try:
            idx = int(example["id"]) - 1  # Convert from 1-based to 0-based indexing
            if 0 <= idx < len(available_examples):
                selected_indices.append(idx)
                selection_reasons[available_examples[idx].name] = example["reason"]
        except (ValueError, KeyError) as e:
            print(f"Warning: Invalid selected example format: {example}, Error: {e}")

    # Process excluded examples
    exclusion_reasons = {}
    for example in result.get("excluded_examples", []):
        try:
            idx = int(example["id"]) - 1  # Convert from 1-based to 0-based indexing
            if 0 <= idx < len(available_examples):
                exclusion_reasons[available_examples[idx].name] = example["reason"]
        except (ValueError, KeyError) as e:
            print(f"Warning: Invalid excluded example format: {example}, Error: {e}")

    selected_examples = [
        available_examples[i]
        for i in selected_indices
        if 0 <= i < len(available_examples)
    ]

    return ExampleSelectionResult(
        selected_examples=selected_examples,
        analysis=analysis,
        selection_reasons=selection_reasons,
        exclusion_reasons=exclusion_reasons,
    )