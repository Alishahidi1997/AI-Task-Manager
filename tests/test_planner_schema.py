"""Unified planner JSON schema (tool_name) for Slack and /chat."""

from app.orchestration.tool_registry import tool_schema_map
from app.services.chat_orchestrator import _tool_registry
from app.validation.json_validator import (
    PlannerOutput,
    normalize_planner_raw,
    validate_chat_planner_output,
    validate_planner_output,
)


def test_normalize_planner_raw_maps_legacy_tool():
    raw = normalize_planner_raw(
        {
            "tool": "update_task",
            "arguments": {"task_id": 1},
            "confidence": 0.9,
        }
    )
    assert raw["tool_name"] == "update_task"
    assert "tool" not in raw


def test_validate_planner_output_accepts_legacy_tool_field():
    schemas = tool_schema_map()
    plan = validate_planner_output(
        {
            "tool": "delete_task",
            "arguments": {"task_id": 42},
            "confidence": 0.95,
            "missing_required": [],
        },
        tool_schemas=schemas,
        allowed_tools=["delete_task"],
    )
    assert isinstance(plan, PlannerOutput)
    assert plan.tool_name == "delete_task"


def test_chat_and_slack_validators_share_planner_output_type():
    slack_plan = validate_planner_output(
        {
            "tool_name": "create_task",
            "arguments": {
                "title": "A",
                "assignee": "u@example.com",
                "due_date": "2099-01-01T00:00:00+00:00",
            },
            "confidence": 0.9,
            "missing_required": [],
        },
        tool_schemas=tool_schema_map(),
        allowed_tools=["create_task"],
    )
    chat_plan = validate_chat_planner_output(
        {
            "tool_name": "create_task",
            "arguments": {"title": "B", "due_date": "2099-01-01T00:00:00+00:00"},
            "confidence": 0.9,
            "missing_required": [],
        },
        tool_registry=_tool_registry(),
    )
    assert type(slack_plan) is type(chat_plan)
    assert slack_plan.tool_name == chat_plan.tool_name == "create_task"
