import json
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

    try:
        if "choices" in response and response["choices"]:
            message = response["choices"][0].get("message", {})
            if isinstance(message, dict):
                content = message.get("content", "")
            else:
                content = str(message)
        else:
            content = str(response)

        if not content.strip():
            content = json.dumps(
                {
                    "analysis": "No analysis provided - LLM returned empty response",
                    "selected_examples": [],
                    "excluded_examples": [],
                }
            )
    except Exception as e:
        raise ValueError(
            f"Failed to extract content from LLM response: {e}\nResponse: {response}"
        )
    from .utils import extract_code_blocks

    try:
        parsed_result = extract_code_blocks(content)
        if parsed_result.code_blocks:
            result = json.loads(parsed_result.code_blocks[0].code)
        else:
            result = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Failed to parse LLM response as JSON: {e}\nResponse: {content}"
        )

    analysis = result.get("analysis", "")

    def _process_example_list(examples, available_examples, is_selected=True):
        indices = []
        reasons_dict = {}

        for example in examples:
            idx = int(example["id"]) - 1
            if 0 <= idx < len(available_examples):
                if is_selected:
                    indices.append(idx)
                reasons_dict[available_examples[idx].name] = example["reason"]

        return indices, reasons_dict

    selected_indices, selection_reasons = _process_example_list(
        result.get("selected_examples", []), available_examples, is_selected=True
    )

    _, exclusion_reasons = _process_example_list(
        result.get("excluded_examples", []), available_examples, is_selected=False
    )

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
