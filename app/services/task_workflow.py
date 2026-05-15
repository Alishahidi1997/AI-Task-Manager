"""Shared task status workflow for REST, /chat, and Slack execution paths."""

ALLOWED_TRANSITIONS = {
    "todo": {"todo", "in_progress"},
    "in_progress": {"in_progress", "done", "todo"},
    "done": {"done", "in_progress"},
}


def assert_status_transition(current_status: str, next_status: str) -> None:
    """Raise ValueError if the transition is not allowed (AI execution paths)."""
    allowed = ALLOWED_TRANSITIONS.get(current_status, set())
    if next_status not in allowed:
        raise ValueError(f"invalid status workflow: {current_status} -> {next_status}")
