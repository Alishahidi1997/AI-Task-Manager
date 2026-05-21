"""Deterministic keyword planner for mocked eval runs (no OpenAI)."""

from __future__ import annotations

import re

from app.evals.models import GoldenCase


def _extract_task_id(text: str, default: int = 1) -> int:
    match = re.search(r"\btask\s*#?\s*(\d+)\b", text, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    match = re.search(r"\bid\s*(\d+)\b", text, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    return default


def _extract_title(text: str) -> str:
    patterns = [
        r'titled?\s+"([^"]+)"',
        r"titled?\s+'([^']+)'",
        r"titled?\s+([^.!?]+)",
        r'called\s+"([^"]+)"',
        r"called\s+([^.!?]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()[:255]
    return "Untitled task"


def _extract_assignee(text: str) -> str:
    email = re.search(r"[\w.+-]+@[\w.-]+\.\w+", text)
    if email:
        return email.group(0)
    match = re.search(r"assign(?:ed)?\s+to\s+([A-Za-z0-9._-]+)", text, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return "teammate@example.com"


def keyword_planner(case: GoldenCase) -> dict:
    text = case.input.lower()
    tool = case.expected_tool
    args: dict = {}

    if tool == "delete_task":
        args = {"task_id": _extract_task_id(case.input)}
    elif tool == "assign_task":
        args = {
            "task_id": _extract_task_id(case.input),
            "assignee": _extract_assignee(case.input),
        }
    elif tool == "update_task":
        args = {"task_id": _extract_task_id(case.input)}
        if "done" in text or "complete" in text:
            args["status"] = "done"
        elif "in progress" in text or "start" in text:
            args["status"] = "in_progress"
        if "due" in text:
            args["due_date"] = "2099-01-15T12:00:00+00:00"
        title = _extract_title(case.input)
        if title != "Untitled task":
            args["title"] = title
    elif tool == "create_task":
        args = {
            "title": _extract_title(case.input),
            "due_date": "2099-01-15T12:00:00+00:00",
        }
        if case.channel == "slack" or "assign" in text:
            args["assignee"] = _extract_assignee(case.input)

    confidence = 0.92
    missing: list[str] = []
    if case.channel == "chat":
        return {
            "tool_name": tool,
            "arguments": args,
            "confidence": confidence,
            "missing_required": missing,
            "clarification_question": None,
        }
    return {
        "tool": tool,
        "arguments": args,
        "confidence": confidence,
        "missing_required": missing,
        "clarification_question": None,
    }
