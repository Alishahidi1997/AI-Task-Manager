from datetime import timedelta

from app.models import DailySummary, Task, User, utcnow


SCENARIOS = {
    "default": {
        "label": "Balanced baseline",
        "description": "A realistic mix of done, in-progress, todo, and overdue tasks.",
    },
    "overdue_sprint": {
        "label": "Overdue sprint",
        "description": "Several sprint items are overdue while key work is still in progress.",
    },
    "churn_risk": {
        "label": "Customer churn risk",
        "description": "High-priority customer follow-ups are delayed and unresolved.",
    },
}


def _clear_demo_data(db, user: User):
    db.query(DailySummary).filter(DailySummary.user_id == user.id).delete()
    db.query(Task).filter(Task.user_id == user.id).delete()


def _build_default_tasks(user: User):
    now = utcnow()
    return [
        Task(
            title="Review API logs and fix timeout issue",
            description="Investigate slow endpoint and patch retry behavior.",
            status="done",
            created_at=now - timedelta(days=3, hours=6),
            due_date=now - timedelta(days=2),
            completed_at=now - timedelta(days=2, hours=5),
            category="today",
            user_id=user.id,
        ),
        Task(
            title="Prepare sprint planning notes",
            description="Summarize carryover and blockers for next sprint.",
            status="done",
            created_at=now - timedelta(days=6),
            due_date=now - timedelta(days=5, hours=4),
            completed_at=now - timedelta(days=5, hours=6),
            category="this_week",
            user_id=user.id,
        ),
        Task(
            title="Refactor task insights chart component",
            description="Simplify props and improve readability.",
            status="in_progress",
            created_at=now - timedelta(days=4),
            due_date=now - timedelta(days=1, hours=3),
            completed_at=None,
            category="this_week",
            user_id=user.id,
        ),
        Task(
            title="Write README deployment section",
            description="Document env vars and deploy steps.",
            status="todo",
            created_at=now - timedelta(days=1),
            due_date=now + timedelta(days=2),
            completed_at=None,
            category="backlog",
            user_id=user.id,
        ),
        Task(
            title="Morning planning and prioritization",
            description="15-minute daily review of deadlines.",
            status="done",
            created_at=now - timedelta(days=2),
            due_date=now - timedelta(days=2),
            completed_at=now - timedelta(days=2, hours=22),
            category="routine",
            user_id=user.id,
        ),
        Task(
            title="Follow up on overdue integration tests",
            description="Stabilize flaky tests in CI pipeline.",
            status="todo",
            created_at=now - timedelta(days=7),
            due_date=now - timedelta(days=1, hours=8),
            completed_at=None,
            category="today",
            user_id=user.id,
        ),
    ]


def _build_overdue_sprint_tasks(user: User):
    now = utcnow()
    return [
        Task(
            title="Finalize sprint backlog grooming",
            description="Close open estimation gaps before sprint review.",
            status="in_progress",
            created_at=now - timedelta(days=5),
            due_date=now - timedelta(days=2),
            completed_at=None,
            category="this_week",
            user_id=user.id,
        ),
        Task(
            title="Fix release blocker: billing webhook retries",
            description="Patch retry policy and replay failed events.",
            status="todo",
            created_at=now - timedelta(days=4),
            due_date=now - timedelta(days=1, hours=6),
            completed_at=None,
            category="today",
            user_id=user.id,
        ),
        Task(
            title="Sprint demo dry run",
            description="Validate stories and updated acceptance criteria.",
            status="done",
            created_at=now - timedelta(days=3),
            due_date=now - timedelta(days=2, hours=4),
            completed_at=now - timedelta(days=2, hours=6),
            category="this_week",
            user_id=user.id,
        ),
        Task(
            title="Resolve QA bug cluster for dashboard filters",
            description="Investigate broken combinations for date + status filters.",
            status="todo",
            created_at=now - timedelta(days=6),
            due_date=now - timedelta(days=3),
            completed_at=None,
            category="backlog",
            user_id=user.id,
        ),
        Task(
            title="Daily standup notes and blocker tracking",
            description="Capture blockers and owners from each standup.",
            status="done",
            created_at=now - timedelta(days=2),
            due_date=now - timedelta(days=2),
            completed_at=now - timedelta(days=2, hours=22),
            category="routine",
            user_id=user.id,
        ),
    ]


def _build_churn_risk_tasks(user: User):
    now = utcnow()
    return [
        Task(
            title="Follow up with Acme Corp renewal owner",
            description="Customer requested pricing clarification 4 days ago.",
            status="todo",
            created_at=now - timedelta(days=6),
            due_date=now - timedelta(days=2),
            completed_at=None,
            category="today",
            user_id=user.id,
        ),
        Task(
            title="Prepare incident RCA for integration outage",
            description="Draft customer-facing summary and next-step actions.",
            status="in_progress",
            created_at=now - timedelta(days=3),
            due_date=now - timedelta(days=1, hours=2),
            completed_at=None,
            category="this_week",
            user_id=user.id,
        ),
        Task(
            title="Schedule executive check-in with Beta Retail",
            description="Escalation requested by account manager.",
            status="todo",
            created_at=now - timedelta(days=5),
            due_date=now - timedelta(days=1, hours=10),
            completed_at=None,
            category="this_week",
            user_id=user.id,
        ),
        Task(
            title="Send recovery plan and timeline to affected accounts",
            description="Include milestones and owner accountability.",
            status="done",
            created_at=now - timedelta(days=4),
            due_date=now - timedelta(days=3),
            completed_at=now - timedelta(days=3, hours=3),
            category="today",
            user_id=user.id,
        ),
        Task(
            title="Weekly customer-health review",
            description="Review risk signals and upcoming renewals.",
            status="done",
            created_at=now - timedelta(days=2),
            due_date=now - timedelta(days=2),
            completed_at=now - timedelta(days=2, hours=20),
            category="routine",
            user_id=user.id,
        ),
    ]


def _build_tasks_for_scenario(scenario_id: str, user: User):
    if scenario_id == "default":
        return _build_default_tasks(user)
    if scenario_id == "overdue_sprint":
        return _build_overdue_sprint_tasks(user)
    if scenario_id == "churn_risk":
        return _build_churn_risk_tasks(user)
    raise ValueError(f"unknown scenario_id '{scenario_id}'")


def list_demo_scenarios():
    return [
        {"id": scenario_id, **metadata}
        for scenario_id, metadata in SCENARIOS.items()
    ]


def load_demo_scenario(db, user: User, scenario_id: str):
    sample_tasks = _build_tasks_for_scenario(scenario_id, user)
    _clear_demo_data(db, user)
    db.add_all(sample_tasks)
    db.commit()
    return {
        "scenario_id": scenario_id,
        "seeded_tasks": len(sample_tasks),
    }


def reset_demo_dataset(db, user: User):
    sample_tasks = _build_default_tasks(user)
    _clear_demo_data(db, user)
    db.add_all(sample_tasks)
    db.commit()

    return {"seeded_tasks": len(sample_tasks)}
