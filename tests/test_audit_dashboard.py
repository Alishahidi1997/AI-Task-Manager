"""Epic 3 audit list + unified trace chain."""

import json

from app.auth import hash_password
from app.database import SessionLocal
from app.models import AuditLog, SlackOrchestrationTrace, User
from tests.conftest import auth_headers, auth_headers_with_role


def test_audit_list_requires_manager(client):
    headers = auth_headers(client, "emp-audit@example.com", "secret123")
    response = client.get("/audit", headers=headers)
    assert response.status_code == 403


def test_audit_list_and_detail_with_trace(client):
    mgr_headers = auth_headers_with_role(
        client, "mgr-audit@example.com", "secret123", role="manager", tenant_id="tenant-audit"
    )
    emp_headers = auth_headers_with_role(
        client, "emp-audit2@example.com", "secret123", role="employee", tenant_id="tenant-audit"
    )

    db = SessionLocal()
    try:
        mgr = db.query(User).filter(User.email == "mgr-audit@example.com").first()
        emp = db.query(User).filter(User.email == "emp-audit2@example.com").first()
        audit = AuditLog(
            request_text="slack: create task",
            tool_name="create_task",
            arguments='{"title":"x"}',
            validation_result="passed",
            execution_result="executed",
            user_id=emp.id,
            tenant_id="tenant-audit",
            slack_event_id="Ev_audit_chain",
        )
        db.add(audit)
        db.commit()
        db.refresh(audit)

        trace = SlackOrchestrationTrace(
            trace_id="trace-pytest-001",
            audit_log_id=audit.id,
            user_id=emp.id,
            tenant_id="tenant-audit",
            slack_channel_id="C_TEST",
            slack_message_ts="1.0",
            slack_user_id="U_TEST",
            outcome="executed",
            total_duration_ms=42,
            spans_json=json.dumps([{"name": "planner", "duration_ms": 10}]),
            metrics_json=json.dumps({"planner_ms": 10}),
        )
        db.add(trace)
        db.commit()
        audit_id = audit.id
    finally:
        db.close()

    listed = client.get("/audit?limit=10", headers=mgr_headers)
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert any(row["id"] == audit_id for row in items)

    detail = client.get(f"/audit/{audit_id}", headers=mgr_headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["execution_result"] == "executed"
    assert body["trace"] is not None
    assert body["trace"]["trace_id"] == "trace-pytest-001"
    assert body["trace"]["spans"][0]["name"] == "planner"

    own = client.get(f"/audit/{audit_id}", headers=emp_headers)
    assert own.status_code == 200
    assert own.json()["trace"]["trace_id"] == "trace-pytest-001"
