from pydantic import BaseModel, Field


class PlannerOutput(BaseModel):
    tool: str = Field(min_length=1, max_length=64)
    arguments: dict
    confidence: float = Field(ge=0.0, le=1.0)
    missing_required: list[str] = Field(default_factory=list)
    clarification_question: str | None = None


def validate_planner_output(raw_payload: dict, *, tool_schemas: dict, allowed_tools: list[str]) -> PlannerOutput:
    payload = PlannerOutput(**raw_payload)
    if payload.tool not in allowed_tools:
        raise ValueError(f"tool '{payload.tool}' is not allowed for this user")
    if payload.tool not in tool_schemas:
        raise ValueError(f"unknown tool '{payload.tool}'")

    schema = tool_schemas[payload.tool]
    required = set(schema.get("required_fields", []))
    optional = set(schema.get("optional_fields", []))
    known = required | optional
    arg_keys = set(payload.arguments.keys())

    missing = sorted(list(required - arg_keys))
    if missing:
        payload.missing_required = sorted(list(set(payload.missing_required) | set(missing)))
        return payload

    extra = sorted(list(arg_keys - known))
    if extra:
        raise ValueError("hallucinated fields: " + ", ".join(extra))

    return payload


def validate_chat_planner_output(raw_payload: dict, *, tool_registry: dict):
    """Structural validation for /chat planner (tool_name + arguments)."""
    from app.services.chat_orchestrator import PlannerOutput as ChatPlannerOutput

    payload = ChatPlannerOutput(**raw_payload)
    if payload.tool_name not in tool_registry:
        raise ValueError(f"tool '{payload.tool_name}' is not allowed for this user")

    schema = tool_registry[payload.tool_name]
    required = set(schema.get("required", []))
    optional = set(schema.get("optional", []))
    known = required | optional
    arg_keys = set(payload.arguments.keys())

    missing = sorted(list(required - arg_keys))
    if missing:
        payload.missing_required = sorted(list(set(payload.missing_required) | set(missing)))
        return payload

    extra = sorted(list(arg_keys - known))
    if extra:
        raise ValueError("hallucinated fields: " + ", ".join(extra))

    return payload
