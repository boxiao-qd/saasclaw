"""spawn_subagent tool — spawn a specialized sub-agent using AgentDefinition + tool filtering."""

import json

from app.agent.delegation.delegate_executor import DelegateExecutor


TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "spawn_subagent",
        "description": "Launch a new agent to handle complex, multi-step tasks. Each agent type has specific capabilities.",
        "parameters": {
            "type": "object",
            "properties": {
                "agent_type": {"type": "string", "description": "Type of agent to spawn (e.g. 'Explore', 'Plan', 'general-purpose')"},
                "goal": {"type": "string", "description": "The task or goal for the spawned agent"},
                "context": {"type": "string", "description": "Additional context or background information"},
            },
            "required": ["agent_type", "goal"],
        },
    },
}


async def execute(args_str: str, employee_id: int) -> str:
    args = json.loads(args_str)
    return json.dumps({"error": "spawn_subagent requires session context — handled by agent_service._execute_tool"}, ensure_ascii=False)


async def execute_with_session(args_str: str, employee_id: int, session_id: str) -> str:
    """Execute spawn_subagent with parent session context."""
    args = json.loads(args_str)
    delegate = DelegateExecutor(employee_id)
    child_id = await delegate.delegate_from_definition(
        parent_session_id=session_id,
        agent_type=args.get("agent_type", ""),
        goal=args.get("goal", ""),
        context=args.get("context"),
    )
    return child_id