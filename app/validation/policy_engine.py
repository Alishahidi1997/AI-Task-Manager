from datetime import datetime, timezone


def enforce_policies(identity_context: dict, tool: str, arguments: dict):
    role = (identity_context.get("role") or "employee").strip().lower()
    tenant = identity_context.get("tenant")
    if not tenant:
        raise PermissionError("tenant context is required")

    assignee = arguments.get("assignee")
    if assignee and role not in {"manager", "admin"}:
        raise PermissionError("only managers/admins can assign tasks")

    due_date = arguments.get("due_date")
    if due_date:
        try:
            parsed = datetime.fromisoformat(str(due_date).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            if parsed < datetime.now(timezone.utc):
                raise PermissionError("due_date cannot be in the past")
        except ValueError:
            raise PermissionError("due_date must be valid ISO datetime")

    if tool == "delete_task" and role not in {"manager", "admin"}:
        raise PermissionError("only managers/admins can delete tasks")

    if arguments.get("priority") == "high" and role not in {"manager", "admin"}:
        raise PermissionError("high priority tasks require manager or admin role")

    if tool == "admin_tools":
        raise PermissionError("admin_tools is not available in this build")
