import json


def test_slack_url_verification(client):
    response = client.post(
        "/slack/events",
        content=json.dumps({"type": "url_verification", "challenge": "pytest-challenge"}),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json() == {"challenge": "pytest-challenge"}


def test_slack_unmapped_user_returns_404(client):
    payload = {
        "type": "event_callback",
        "event": {
            "type": "message",
            "user": "U_UNMAPPED_PYTEST",
            "text": "create a task",
            "channel": "C_TEST",
            "ts": "123.456",
        },
    }
    response = client.post(
        "/slack/events",
        content=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 404
    detail = response.json()["detail"]
    if isinstance(detail, dict):
        assert "slack user" in detail.get("detail", "").lower() or "mapped" in detail.get("detail", "").lower()
