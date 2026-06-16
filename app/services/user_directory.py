"""Tenant-scoped workspace user directory for assignee resolution and planner hints."""

from __future__ import annotations


def _normalize_hint(hint: str) -> str:
    return hint.strip().lower()


def _email_local(email: str) -> str:
    return email.split("@", 1)[0].lower()


def _looks_like_email(value: str) -> bool:
    return "@" in value.strip()


def effective_display_name(user) -> str:
    name = (getattr(user, "display_name", None) or "").strip()
    if name:
        return name
    return _email_local(user.email)


def list_workspace_directory(db, tenant_id: str) -> list[dict]:
    from app.models import User

    rows = (
        db.query(User)
        .filter(User.tenant_id == tenant_id)
        .order_by(User.email)
        .all()
    )
    return [
        {
            "id": user.id,
            "email": user.email,
            "display_name": effective_display_name(user),
            "role": user.role,
        }
        for user in rows
    ]


def planner_assignable_users(db, tenant_id: str) -> list[dict]:
    """Compact assignee hints for LLM planners (manager/admin surfaces)."""
    return [
        {"name": entry["display_name"], "email": entry["email"]}
        for entry in list_workspace_directory(db, tenant_id)
    ]


def find_assignee_candidates(db, tenant_id: str, hint: str):
    """Match assignee hints by display name, email local-part, or slack id."""
    from app.models import User

    needle = _normalize_hint(hint)
    if not needle:
        return []

    rows = db.query(User).filter(User.tenant_id == tenant_id).all()
    if _looks_like_email(needle):
        return [user for user in rows if user.email.lower() == needle]

    exact: list = []
    prefix: list = []
    seen: set[int] = set()

    def add_exact(user) -> None:
        if user.id not in seen:
            seen.add(user.id)
            exact.append(user)

    def add_prefix(user) -> None:
        if user.id not in seen:
            seen.add(user.id)
            prefix.append(user)

    for user in rows:
        if user.slack_user_id and user.slack_user_id.lower() == needle:
            add_exact(user)
            continue
        if user.email.lower() == needle:
            add_exact(user)
            continue

        local = _email_local(user.email)
        if local == needle:
            add_exact(user)
        elif local.startswith(needle):
            add_prefix(user)

        display = (user.display_name or "").strip().lower()
        if display:
            if display == needle:
                add_exact(user)
            elif display.startswith(needle):
                add_prefix(user)

    if exact:
        return exact
    return prefix


def find_tenant_user(db, tenant: str, assignee: str):
    """Resolve a tenant user by email, slack id, or exact display name."""
    from app.models import User

    needle = assignee.strip().lower()
    if not needle:
        return None

    rows = db.query(User).filter(User.tenant_id == tenant).all()
    for user in rows:
        if user.email.lower() == needle:
            return user
        if user.slack_user_id and user.slack_user_id.lower() == needle:
            return user
        display = (user.display_name or "").strip().lower()
        if display and display == needle:
            return user
    return None
