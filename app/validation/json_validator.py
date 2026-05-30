from pydantic import BaseModel, Field


class PlannerOutput(BaseModel):
    tool_name: str = Field(min_length=1, max_length=64)
    arguments: dict
    confidence: float = Field(ge=0.0, le=1.0)
    missing_required: list[str] = Field(default_factory=list)
    clarification_question: str | None = None


def normalize_planner_raw(raw: dict) -> dict:
    """Accept legacy Slack planner field ``tool``; canonical key is ``tool_name``."""
    out = dict(raw)
    if out.get("tool_name"):
        out.pop("tool", None)
        return out
    if out.get("tool"):
        out["tool_name"] = out.pop("tool")
    return out


def _chat_registry_to_schemas(tool_registry: dict) -> dict:
    return {
        name: {
            "required_fields": list(schema.get("required", [])),
            "optional_fields": list(schema.get("optional", [])),
        }
        for name, schema in tool_registry.items()
    }


def validate_planner_output(
    raw_payload: dict,
    *,
    tool_schemas: dict,
    allowed_tools: list[str],
) -> PlannerOutput:
    payload = PlannerOutput(**normalize_planner_raw(raw_payload))
    if payload.tool_name not in allowed_tools:
        raise ValueError(f"tool '{payload.tool_name}' is not allowed for this user")
    if payload.tool_name not in tool_schemas:
        raise ValueError(f"unknown tool '{payload.tool_name}'")

    schema = tool_schemas[payload.tool_name]
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


def validate_chat_planner_output(raw_payload: dict, *, tool_registry: dict) -> PlannerOutput:
    """Structural validation for /chat planner (same schema as Slack)."""
    return validate_planner_output(
        raw_payload,
        tool_schemas=_chat_registry_to_schemas(tool_registry),
        allowed_tools=list(tool_registry.keys()),
    )
