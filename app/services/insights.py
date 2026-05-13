# productivity numbers from done tasks (needs completed_at filled when they hit done)
from datetime import datetime, timedelta, timezone

from app.services.analytics import detect_kpi_anomalies


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


def build_insight_explanation(insight_id, done_tasks, pending_tasks, guess_fn):
    now = datetime.now(timezone.utc)
    if insight_id == "productivity":
        rows = build_productivity_insights(done_tasks, guess_fn).get("buckets", [])
        if not rows:
            return {
                "insight_id": insight_id,
                "title": "Why productivity insight is limited",
                "why": [
                    "There are not enough completed tasks with valid timestamps yet.",
                    "Productivity insight needs both created and completed times to calculate speed.",
                    "Mark more tasks as done to improve confidence and bucket comparisons.",
                ],
                "generated_at": now.isoformat(),
            }
        fastest = rows[0]
        slowest = rows[-1]
        return {
            "insight_id": insight_id,
            "title": "Why this productivity insight was generated",
            "why": [
                f"Completed tasks are grouped by planning bucket such as '{fastest['category']}'.",
                "For each bucket, completion speed is calculated using completed_at - created_at.",
                f"Current fastest bucket is '{fastest['category']}' at {fastest['avg_hours_to_complete']}h average.",
                f"Current slowest bucket is '{slowest['category']}' at {slowest['avg_hours_to_complete']}h average.",
            ],
            "generated_at": now.isoformat(),
        }

    if insight_id == "priority":
        data = build_priority_suggestions(pending_tasks, guess_fn)
        tasks = data.get("tasks", [])
        if not tasks:
            return {
                "insight_id": insight_id,
                "title": "Why priority suggestions look healthy",
                "why": [
                    "No open task is currently overdue.",
                    "Priority insight only escalates tasks where due_date is in the past and status is not done.",
                    "As soon as overdue items appear, they are ranked by urgency.",
                ],
                "generated_at": now.isoformat(),
            }

        highest = max(tasks, key=lambda t: t["hours_overdue"])
        high_count = sum(1 for t in tasks if t["priority"] == "high")
        return {
            "insight_id": insight_id,
            "title": "Why these tasks are prioritized",
            "why": [
                "Only open tasks with due dates in the past are included in this insight.",
                "Priority level is based on overdue hours (>=72h high, >=24h medium, otherwise low).",
                f"There are {high_count} high-priority overdue task(s) in the current result set.",
                f"Most overdue task is '{highest['title']}' at {highest['hours_overdue']}h overdue.",
            ],
            "generated_at": now.isoformat(),
        }

    return None


def build_anomalies_explanation(tasks, window_days: int, baseline_days: int):
    """User-facing 'why' for KPI anomaly detection (same detector as GET /insights/anomalies)."""
    now = datetime.now(timezone.utc)
    data = detect_kpi_anomalies(tasks, window_days=window_days, baseline_days=baseline_days)
    snaps = int(data.get("snapshots_used") or 0)
    w = int(data.get("window_days") or window_days)
    b = int(data.get("baseline_days") or baseline_days)
    why = [
        f"Anomalies use the last {w} calendar days of daily KPI snapshots built from your tasks.",
        (
            f"Each day is compared to the prior {b}-day rolling baseline using z-scores; "
            "a day flags when |z| >= 2.0 and the move is material for that metric."
        ),
        "Metrics are completions that day, open overdue count at end of day, and average "
        "create-to-done hours for tasks completed that day (when enough signal exists).",
    ]
    if snaps < b + 1:
        why.append(
            f"Only {snaps} snapshot day(s) are usable right now; need at least {b + 1} days "
            "spanning the window to compare each day against a full baseline."
        )
    flagged = data.get("anomalies") or []
    top = flagged[:3]
    if top:
        why.append("Strongest current flags by impact:")
        for row in top:
            day = str(row.get("date", ""))[:10]
            why.append(
                f"- {row.get('metric')} {row.get('direction')} on {day} "
                f"(z={row.get('z_score')}, confidence {row.get('confidence')}, impact {row.get('impact')})."
            )
    else:
        why.append(
            "No day in this window exceeded the threshold—either steady day-to-day patterns "
            "or not enough variance yet for a confident flag."
        )
    return {
        "insight_id": "anomalies",
        "title": "How KPI anomaly detection works",
        "why": why,
        "generated_at": data.get("generated_at") or now.isoformat(),
    }


def _next_action_type(task, hours_overdue: float):
    title = (getattr(task, "title", "") or "").lower()
    if "contact" in title or "customer" in title or "client" in title:
        return "contact_owner"
    if hours_overdue >= 72:
        return "escalate_risk"
    if hours_overdue >= 36:
        return "split_task"
    return "reschedule"


def _action_text(action_type: str, task):
    if action_type == "contact_owner":
        return f"Contact the owner for '{task.title}' and confirm a concrete recovery ETA."
    if action_type == "escalate_risk":
        return f"Escalate risk for '{task.title}' because delay is severe and likely impacts commitments."
    if action_type == "split_task":
        return f"Split '{task.title}' into a smaller deliverable and close one subtask today."
    return f"Reschedule '{task.title}' with a realistic due date and mark the blocker in notes."


def _learned_multiplier(action_type: str, feedback_rows):
    accepted = 0
    dismissed = 0
    completed = 0
    for row in feedback_rows:
        if row.action_type != action_type:
            continue
        if row.outcome == "accepted":
            accepted += 1
        elif row.outcome == "dismissed":
            dismissed += 1
        elif row.outcome == "completed":
            completed += 1

    attempts = accepted + dismissed + completed
    if attempts == 0:
        return 1.0
    success_rate = (completed + 0.5 * accepted) / attempts
    penalty_rate = dismissed / attempts
    # bounded adaptive multiplier so feedback nudges rank without overfitting
    return max(0.75, min(1.35, 1.0 + 0.45 * (success_rate - penalty_rate)))


def build_next_actions(tasks, feedback_rows, guess_fn):
    now = datetime.now(timezone.utc)
    rows = []
    for task in tasks:
        due_utc = _as_utc(getattr(task, "due_date", None))
        if due_utc is None:
            continue
        if due_utc >= now:
            continue
        if getattr(task, "status", "") == "done":
            continue

        overdue_hours = round((now - due_utc).total_seconds() / 3600.0, 2)
        action_type = _next_action_type(task, overdue_hours)
        base_impact = overdue_hours * (1.4 if action_type == "escalate_risk" else 1.0)
        learned = _learned_multiplier(action_type, feedback_rows)
        rank_score = round(base_impact * learned, 3)
        feedback_key = f"{action_type}:{task.id}"
        rows.append(
            {
                "id": feedback_key,
                "task_id": task.id,
                "task_title": task.title,
                "category": _bucket_for_task(task, guess_fn),
                "hours_overdue": overdue_hours,
                "action_type": action_type,
                "action": _action_text(action_type, task),
                "rank_score": rank_score,
                "feedback_key": feedback_key,
                "learned_multiplier": round(learned, 3),
            }
        )

    rows.sort(key=lambda row: row["rank_score"], reverse=True)
    top = rows[:20]
    return {
        "generated_at": now.isoformat(),
        "suggestion": (
            "Top actions are ranked by overdue impact and adjusted using your historical outcomes "
            "(accepted, dismissed, completed)."
        ),
        "total_candidates": len(rows),
        "actions": top,
    }
