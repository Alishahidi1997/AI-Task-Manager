from datetime import datetime, timedelta, timezone

from tests.conftest import auth_headers


def test_task_crud(client):
    headers = auth_headers(client, "tasks-user@example.com", "secret123")
    due = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

    created = client.post(
        "/tasks",
        headers=headers,
        json={"title": "Write tests", "description": "pytest coverage", "due_date": due},
    )
    assert created.status_code == 201
    task = created.json()
    task_id = task["id"]
    assert task["title"] == "Write tests"
    assert task["status"] == "todo"

    listed = client.get("/tasks", headers=headers)
    assert listed.status_code == 200
    assert any(row["id"] == task_id for row in listed.json())

    one = client.get(f"/tasks/{task_id}", headers=headers)
    assert one.status_code == 200

    updated = client.put(f"/tasks/{task_id}", headers=headers, json={"status": "in_progress"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "in_progress"

    deleted = client.delete(f"/tasks/{task_id}", headers=headers)
    assert deleted.status_code == 204

    missing = client.get(f"/tasks/{task_id}", headers=headers)
    assert missing.status_code == 404
