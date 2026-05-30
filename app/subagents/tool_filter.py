"""Tool filter for sub-agents — three-layer filtering aligned with cc-source resolveAgentTools."""

from app.subagents.agent_definition import AgentDefinition, AgentSource

# Tools NEVER available to any sub-agent (prevents recursive delegation)
GLOBAL_DISALLOWED_TOOLS: frozenset[str] = frozenset({
    "spawn_subagent",
})


def filter_tools_for_agent(
    all_tools: list[dict],
    agent_def: AgentDefinition,
) -> list[dict]:
    """Filter available tools for a specific agent definition.

    Three layers (in order):
    1. Global disallowed — spawn_subagent always excluded
    2. Per-agent disallowed_tools — agent-specific denylist
    3. Per-agent tools allowlist — if set, only return matching tools

    Returns filtered list of TOOL_DEF dicts.
    """
    disallowed: set[str] = set(GLOBAL_DISALLOWED_TOOLS)

    if agent_def.disallowed_tools:
        disallowed.update(agent_def.disallowed_tools)

    filtered = [t for t in all_tools if t["function"]["name"] not in disallowed]

    if agent_def.tools is not None and not (
        len(agent_def.tools) == 1 and agent_def.tools[0] == "*"
    ):
        allowed = set(agent_def.tools) - disallowed
        filtered = [t for t in filtered if t["function"]["name"] in allowed]

    return filtered