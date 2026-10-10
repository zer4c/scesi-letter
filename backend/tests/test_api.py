from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_list_and_run_automation() -> None:
    created = client.post(
        "/api/automations",
        json={"name": "Daily report", "action": "generate_report"},
    )
    assert created.status_code == 201
    automation = created.json()

    listed = client.get("/api/automations")
    assert listed.status_code == 200
    assert any(item["id"] == automation["id"] for item in listed.json())

    run = client.post(f"/api/automations/{automation['id']}/run")
    assert run.status_code == 200
    assert run.json()["status"] == "completed"
