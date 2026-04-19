# daily-style buckets (not "backend vs frontend")
from datetime import datetime, timedelta, timezone


def _due_as_utc(due_date):
    if due_date is None:
        return None
    if due_date.tzinfo is None:
        return due_date.replace(tzinfo=timezone.utc)
    return due_date


def guess_category(title: str, description: str, due_date=None) -> str:
    blob = (title + " " + (description or "")).lower()

    routine_hits = (
        "routine",
        "habit",
        "daily",
        "every day",
        "everyday",
        "morning",
        "evening",
        "walk",
        "gym",
        "water",
        "stretch",
    )
    if any(w in blob for w in routine_hits):
        return "routine"

    urgent_hits = ("asap", "urgent", "today", "eod", "now", "immediately", "right away")
    if any(w in blob for w in urgent_hits):
        return "today"

    d = _due_as_utc(due_date)
    if d is not None:
        today = datetime.now(timezone.utc).date()
        due = d.date()
        if due <= today:
            return "today"
        if due <= today + timedelta(days=7):
            return "this_week"
        return "backlog"

    return "backlog"
