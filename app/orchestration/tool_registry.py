TOOLS = [
    {
        "name": "create_task",
        "description": "Create a task for a user",
        "required_fields": ["assignee", "title", "due_date"],
        "optional_fields": ["priority"],
    },
    {
        "name": "update_task",
        "description": "Update an existing task",
        "required_fields": ["task_id"],
        "optional_fields": ["status", "assignee", "due_date", "title", "description"],
    },
    {
        "name": "assign_task",
        "description": "Assign a task to a user",
        "required_fields": ["task_id", "assignee"],
        "optional_fields": [],
    },
    {
        "name": "delete_task",
        "description": "Delete a task",
        "required_fields": ["task_id"],
        "optional_fields": [],
    },
    {
        "name": "admin_tools",
        "description": "Administrative operations",
        "required_fields": ["action"],
        "optional_fields": ["payload"],
    },
]


def filter_tools(allowed_tool_names: list[str]) -> list[dict]:
    allow = set(allowed_tool_names)
    return [tool for tool in TOOLS if tool["name"] in allow]


def tool_schema_map() -> dict[str, dict]:
    return {tool["name"]: tool for tool in TOOLS}
