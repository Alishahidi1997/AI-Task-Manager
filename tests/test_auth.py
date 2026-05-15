from tests.conftest import auth_headers


def test_register_login_and_me(client):
    headers = auth_headers(client, "pytest-user@example.com", "secret123")
    me = client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == "pytest-user@example.com"
    assert "id" in body


def test_login_wrong_password(client):
    client.post("/auth/register", json={"email": "wrong-pw@example.com", "password": "correct"})
    bad = client.post("/auth/login", json={"email": "wrong-pw@example.com", "password": "nope"})
    assert bad.status_code == 401
