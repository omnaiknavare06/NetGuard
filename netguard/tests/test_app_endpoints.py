from app import app


def test_health_endpoint_shape() -> None:
    client = app.test_client()
    response = client.get("/api/health")

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert "capacity_mode" in data
    assert "active_sessions" in data


def test_incidents_export_endpoint_shape() -> None:
    client = app.test_client()
    response = client.get("/api/incidents/export?limit=5")

    assert response.status_code == 200
    data = response.get_json()
    assert "exported_at" in data
    assert "count" in data
    assert isinstance(data["incidents"], list)


def test_capacity_config_endpoint_updates_limits() -> None:
    client = app.test_client()
    response = client.post("/api/config/capacity", json={"max_normal": 12, "max_reject": 20})

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert data["max_normal"] == 12
    assert data["max_reject"] == 20


def test_ai_report_endpoint_shape() -> None:
    client = app.test_client()
    response = client.get("/api/ai/report")

    assert response.status_code == 200
    data = response.get_json()
    assert "total_incidents" in data
    assert "gemini_enriched" in data
    assert "agent_usage" in data
