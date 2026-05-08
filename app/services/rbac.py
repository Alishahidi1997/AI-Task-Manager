ROLE_TOOL_ALLOWLIST = {
    "employee": {"create_task", "update_task"},
    "manager": {"create_task", "update_task", "assign_task", "delete_task"},
    "admin": {"create_task", "update_task", "assign_task", "delete_task", "admin_tools"},
}


def allowed_tools_for_role(role: str) -> list[str]:
    key = (role or "employee").strip().lower()
    tools = ROLE_TOOL_ALLOWLIST.get(key, ROLE_TOOL_ALLOWLIST["employee"])
    return sorted(list(tools))
