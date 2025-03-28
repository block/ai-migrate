"""Utilities for generating system prompts and other common tasks."""

from typing import Optional, List
from pydantic import BaseModel


class PRDetails(BaseModel):
    title: str
    body: str
    files: List[dict]
    additions: int
    deletions: int


async def generate_system_prompt(
    description: str, pr_details: Optional[PRDetails] = None
) -> str:
    from ai_migrate.llm_providers import DefaultClient

    client = DefaultClient()

    system_prompt = """You are an expert at creating system prompts for code migration tasks.
Your goal is to create clear, actionable system prompts that will guide an AI to perform code migrations.
Focus on extracting key patterns and transformation rules."""

    context = f"Description: {description}\n\n"
    if pr_details:
        context += f"""
Pull Request Title: {pr_details.title}
Pull Request Description: {pr_details.body}

Files Changed: {len(pr_details.files)}
Total Additions: {pr_details.additions}
Total Deletions: {pr_details.deletions}
"""

    user_prompt = f"""
I need to create a system prompt for a code migration task. Here are the details:

{context}
Create a comprehensive system prompt that includes:

1. Migration Overview:
   - Clear statement of the migration goal
   - Context and motivation for the changes
   - Expected outcome

2. Transformation Rules:
   - Specific patterns to identify in the code
   - Step-by-step transformation instructions
   - Examples of before/after patterns if possible

3. Technical Details:
   - Required code changes
   - Dependencies or imports to update
   - API changes or replacements

4. Constraints and Considerations:
   - Edge cases to handle
   - Performance implications
   - Backward compatibility requirements
   - Code style guidelines

Make the prompt clear and actionable, focusing on practical guidance for the migration.
Avoid vague instructions - provide specific patterns and rules where possible.
"""

    return await client.generate_text(system_prompt, user_prompt)
