def test_metrics_endpoint_exposes_prometheus_text(client):
    client.get("/")
    response = client.get("/metrics")
    assert response.status_code == 200
    body = response.text
    assert "http_requests_total" in body
    assert "openai_planner_requests_total" in body
