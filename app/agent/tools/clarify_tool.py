"""clarify tool — ask the user clarifying questions (multiple-choice or open-ended)."""

import json

MAX_CHOICES = 4

TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "clarify",
        "description": (
            "Ask the user a clarifying question when the task is ambiguous, has multiple viable approaches, "
            "or needs a decision with trade-offs. Supports two modes: multiple-choice (up to 4 options, "
            "UI auto-appends 'Other') or open-ended (omit choices). Do NOT use for yes/no confirmation of "
            "dangerous commands. Present the question clearly and wait for the user's answer."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to present to the user",
                },
                "choices": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 4,
                    "description": "Up to 4 predefined answer choices. Omit for open-ended question.",
                },
            },
            "required": ["question"],
        },
    },
}


async def execute(args_str: str, employee_id: int) -> str:
    args = json.loads(args_str)
    question = args.get("question", "").strip()
    choices = args.get("choices") or []

    if not question:
        return json.dumps({"error": "Question cannot be empty"}, ensure_ascii=False)

    # Normalize choices: trim, limit to MAX_CHOICES, remove empty
    if choices:
        choices = [c.strip() for c in choices if c.strip()]
        choices = choices[:MAX_CHOICES]
        if not choices:
            choices = None  # Fall back to open-ended

    return json.dumps({
        "question": question,
        "choices_offered": choices,
        "mode": "multiple_choice" if choices else "open_ended",
        "instruction": (
            "Present this question to the user clearly. If choices are provided, list them as numbered "
            "options and also offer 'Other (type your answer)' as an extra option. Wait for the user's "
            "response in their next message before proceeding."
        ),
    }, ensure_ascii=False)