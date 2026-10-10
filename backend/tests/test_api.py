from types import SimpleNamespace

from fastapi.testclient import TestClient
from pycrdt import Doc, Map

from app.main import app
from app.modules.auth.routes import require_current_user
from app.modules.collaboration.services import CollaborationService
from app.modules.document.schemas import DocumentCreate, LetterFields
from app.modules.event.services import EventService


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


def test_new_document_can_start_with_an_empty_body() -> None:
    draft = DocumentCreate(
        metadata=LetterFields(document_type="SOL", date="2026-10-10"),
        body="",
    )
    assert draft.body == ""


def test_partial_collaborative_party_fields_remain_a_valid_draft() -> None:
    document = Doc()
    document["metadata"] = Map(
        {
            "document_type": "SOL",
            "date": "2026-10-10",
            "recipient_name": "",
            "recipient_role": "Director de carrera",
            "recipient_institution": "UMSS",
            "recipient_career": "Sistemas",
            "recipient_email": "",
        }
    )

    metadata = CollaborationService._parse_metadata(document)

    assert metadata.recipient is None


def test_event_slug_is_stable_and_normalized() -> None:
    assert EventService._slug("Jornada de Sistemas 2026") == "jornada-de-sistemas-2026"
