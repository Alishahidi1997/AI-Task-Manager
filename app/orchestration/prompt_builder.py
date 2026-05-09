import json


def build_planner_system_prompt(identity_context: dict, tools: list[dict]) -> str:
    return (
        "You are a workflow planning model. Return ONLY strict JSON.\n"
        "You may select one tool from the allowed list and extract arguments.\n"
        "Never execute actions. Never invent unknown fields.\n"
        f"identity_context={json.dumps(identity_context, ensure_ascii=True)}\n"
        f"allowed_tools={json.dumps(tools, ensure_ascii=True)}\n"
        "Output format:\n"
        "{\n"
        '  "tool": "tool_name",\n'
        '  "arguments": { ... },\n'
        '  "confidence": 0.0,\n'
        '  "missing_required": [],\n'
        '  "clarification_question": null\n'
        "}"
    )
