from __future__ import annotations

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    register_harness_profile,
)

VILLAGE_EXCLUDED_TOOLS = frozenset(
    {
        "write_todos",
        "ls",
        "read_file",
        "write_file",
        "edit_file",
        "glob",
        "grep",
        "execute",
        "task",
    }
)

VILLAGE_BASE_SYSTEM_PROMPT = """\
You are a villager in an emergent village simulation.

Each turn you must choose exactly one action for the current tick.
Respond with structured output matching the action schema in the user message.
Do not call tools, plan with todos, read files, or spawn subagents.
Pick a single action that advances your goals while respecting village constraints.\
"""


def village_harness_profile() -> HarnessProfile:
    return HarnessProfile(
        base_system_prompt=VILLAGE_BASE_SYSTEM_PROMPT,
        excluded_tools=VILLAGE_EXCLUDED_TOOLS,
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
        excluded_middleware=frozenset(
            {
                "SummarizationMiddleware",
                "TodoListMiddleware",
            }
        ),
    )


def register_village_harness(model_key: str) -> None:
    register_harness_profile(model_key, village_harness_profile())
