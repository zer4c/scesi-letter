from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.modules.auth.routes import require_current_user


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


def test_membership_list_rejects_non_admin() -> None:
    app.dependency_overrides[require_current_user] = lambda: SimpleNamespace(
        role="user"
    )
    try:
        response = client.get("/api/users")
    finally:
        app.dependency_overrides.pop(require_current_user, None)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
