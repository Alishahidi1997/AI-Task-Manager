# productivity numbers from done tasks (needs completed_at filled when they hit done)
from datetime import datetime, timedelta, timezone


def _bucket_for_task(task, guess_fn):
    if getattr(task, "category", None):
        return task.category
    return guess_fn(task.title, task.description or "", getattr(task, "due_date", None))


def build_productivity_insights(done_tasks, guess_fn):
    # done_tasks: ORM rows with completed_at set
    buckets = {}
    for t in done_tasks:
        if t.completed_at is None or t.created_at is None:
            continue
        cat = _bucket_for_task(t, guess_fn)
        secs = (t.completed_at - t.created_at).total_seconds()
        if secs < 0:
            continue
        hours = secs / 3600.0
        if cat not in buckets:
            buckets[cat] = {"count": 0, "total_hours": 0.0}
        buckets[cat]["count"] += 1
        buckets[cat]["total_hours"] += hours

    rows = []
    for cat, data in buckets.items():
        c = data["count"]
        avg = data["total_hours"] / c if c else 0.0
        rows.append(
            {
                "category": cat,
                "tasks_completed": c,
                "avg_hours_to_complete": round(avg, 2),
            }
        )

    rows.sort(key=lambda r: r["avg_hours_to_complete"])

    narrative = ""
    if len(rows) >= 2:
        fastest = rows[0]["category"]
        slowest = rows[-1]["category"]
        a0 = rows[0]["avg_hours_to_complete"]
        a1 = rows[-1]["avg_hours_to_complete"]
        if a0 == a1:
            narrative = (
                f"Buckets '{fastest}' and '{slowest}' look about the same speed right now "
                f"(avg {a0}h). Need more spread in real timing to say one is faster."
            )
        else:
            narrative = (
                f"You tend to complete {fastest} tasks faster than {slowest} tasks "
                f"(avg {a0}h vs {a1}h)."
            )
    elif len(rows) == 1:
        narrative = (
            f"Only enough history in the '{rows[0]['category']}' bucket so far "
            f"(avg {rows[0]['avg_hours_to_complete']}h to complete)."
        )
    else:
        narrative = "Not enough completed tasks with timestamps yet. Mark tasks done and try again."

    return {"buckets": rows, "narrative": narrative}


def _as_utc(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _priority_label(hours_overdue: float) -> str:
    if hours_overdue >= 72:
        return "high"
    if hours_overdue >= 24:
        return "medium"
    return "low"


def build_priority_suggestions(tasks, guess_fn):
    now = datetime.now(timezone.utc)
    overdue = []
    for t in tasks:
        due_utc = _as_utc(getattr(t, "due_date", None))
        if due_utc is None:
            continue
        if due_utc >= now:
            continue
        if getattr(t, "status", "") == "done":
            continue

        overdue_hours = round((now - due_utc).total_seconds() / 3600.0, 2)
        overdue.append(
            {
                "id": t.id,
                "title": t.title,
                "status": t.status,
                "due_date": due_utc.isoformat(),
                "category": _bucket_for_task(t, guess_fn),
                "hours_overdue": overdue_hours,
                "priority": _priority_label(overdue_hours),
            }
        )

    overdue.sort(key=lambda row: row["due_date"])
    top = overdue[:20]

    if not top:
        suggestion = "No overdue tasks right now. You're on track."
    else:
        high = sum(1 for t in top if t["priority"] == "high")
        suggestion = (
            f"Focus on the oldest overdue tasks first. "
            f"You have {len(top)} overdue task(s) in this view, including {high} high-priority item(s)."
        )

    return {
        "generated_at": now.isoformat(),
        "total_overdue": len(overdue),
        "suggestion": suggestion,
        "tasks": top,
    }


def build_weekly_retro(done_tasks, open_tasks, guess_fn):
    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=7)

    completed_this_week = []
    for t in done_tasks:
        done_at = _as_utc(getattr(t, "completed_at", None))
        if done_at is None:
            continue
        if done_at >= week_start:
            completed_this_week.append(t)

    overdue_open = []
    for t in open_tasks:
        due_utc = _as_utc(getattr(t, "due_date", None))
        if due_utc is None:
            continue
        if due_utc < now and getattr(t, "status", "") != "done":
            overdue_open.append((t, due_utc))

    done_by_bucket = {}
    for t in completed_this_week:
        cat = _bucket_for_task(t, guess_fn)
        done_by_bucket[cat] = done_by_bucket.get(cat, 0) + 1

    overdue_by_bucket = {}
    for t, _ in overdue_open:
        cat = _bucket_for_task(t, guess_fn)
        overdue_by_bucket[cat] = overdue_by_bucket.get(cat, 0) + 1

    top_done_bucket = max(done_by_bucket.items(), key=lambda x: x[1])[0] if done_by_bucket else None
    top_slip_bucket = (
        max(overdue_by_bucket.items(), key=lambda x: x[1])[0] if overdue_by_bucket else None
    )

    if completed_this_week:
        went_well = (
            f"You completed {len(completed_this_week)} task(s) this week. "
            + (
                f"Strongest momentum was in '{top_done_bucket}' work."
                if top_done_bucket
                else "Nice steady execution across your tasks."
            )
        )
    else:
        went_well = "You did not complete tasks this week yet, but your planning data is in place."

    if overdue_open:
        oldest_task, oldest_due = min(overdue_open, key=lambda pair: pair[1])
        slipped = (
            f"{len(overdue_open)} task(s) are overdue right now. "
            + (
                f"Most slippage is in '{top_slip_bucket}' tasks. "
                if top_slip_bucket
                else ""
            )
            + f"Oldest overdue item: '{oldest_task.title}' (due {oldest_due.date().isoformat()})."
        )
    else:
        slipped = "No overdue tasks this week. Delivery risk looks controlled."

    if overdue_open:
        focus = (
            "Next week focus: clear the oldest overdue tasks first, then protect one daily block "
            "for high-priority work before adding new tasks."
        )
    else:
        focus = (
            "Next week focus: keep this pace and prioritize strategic tasks by setting 2-3 "
            "must-complete items at the start of each day."
        )

    return {
        "generated_at": now.isoformat(),
        "window_days": 7,
        "metrics": {
            "completed_this_week": len(completed_this_week),
            "overdue_open_tasks": len(overdue_open),
            "top_completed_bucket": top_done_bucket,
            "top_slipping_bucket": top_slip_bucket,
        },
        "what_went_well": went_well,
        "what_slipped": slipped,
        "next_week_focus": focus,
    }
