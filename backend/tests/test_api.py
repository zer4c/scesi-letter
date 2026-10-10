from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pycrdt import Doc, Map
from pydantic import ValidationError

from app.core.database import get_mongo_client
from app.main import app
from app.modules.auth.routes import require_current_user
from app.modules.collaboration.services import CollaborationService
from app.modules.document.schemas import DocumentCreate, LetterFields
from app.modules.event.services import EventService
from app.modules.signature.schemas import SignatureEnvelopeInput

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_fake_automation_success_endpoint_is_removed() -> None:
    response = client.post("/api/automations/00000000-0000-0000-0000-000000000001/run")
    assert response.status_code == 404


def test_letter_assistance_routes_require_a_privacy_preview_and_decisions():
    paths = app.openapi()["paths"]

    assert "post" in paths["/api/documents/{document_id}/analyze/preview"]
    assert "post" in paths["/api/documents/{document_id}/analyze"]
    assert "get" in paths["/api/documents/{document_id}/suggestions"]
    assert (
        "post"
        in paths["/api/documents/{document_id}/suggestions/{suggestion_id}/accept"]
    )


def test_contact_directory_supports_selected_record_reload():
    paths = app.openapi()["paths"]
    assert "get" in paths["/api/contacts"]
    assert "post" in paths["/api/contacts"]
    assert "get" in paths["/api/contacts/{contact_id}"]
    assert "patch" in paths["/api/contacts/{contact_id}"]


def test_gmail_dispatch_and_scoped_job_status_routes_exist():
    paths = app.openapi()["paths"]
    assert "post" in paths["/api/mail/send"]
    assert "get" in paths["/api/jobs/{job_id}"]


def test_selected_version_can_be_finalized_explicitly():
    paths = app.openapi()["paths"]
    assert "post" in paths["/api/documents/{document_id}/versions/{version_id}/finalize"]
    assert (
        "post"
        in paths["/api/documents/{document_id}/suggestions/{suggestion_id}/reject"]
    )


def test_organization_settings_routes_are_available():
    paths = app.openapi()["paths"]
    assert "get" in paths["/api/users"]
    assert "patch" in paths["/api/users/{user_id}"]
    assert "post" in paths["/api/auth/invitations"]
    assert "get" in paths["/api/auth/invitations"]
    assert "get" in paths["/api/template"]
    assert "patch" in paths["/api/template"]
    assert "post" in paths["/api/integrations/google/connect"]
    assert "get" in paths["/api/integrations/google/callback"]


def test_denied_google_consent_returns_to_organization_settings():
    app.dependency_overrides[require_current_user] = lambda: SimpleNamespace(
        role="admin"
    )
    app.dependency_overrides[get_mongo_client] = lambda: None
    try:
        response = client.get(
            "/api/integrations/google/callback?error=access_denied",
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.pop(require_current_user, None)
        app.dependency_overrides.pop(get_mongo_client, None)

    assert response.status_code == 303
    assert response.headers["location"].endswith(
        "/settings/organization?connection=denied"
    )


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


def test_signature_envelope_requires_fixed_kdf_and_gcm_sizes() -> None:
    import base64

    envelope = {
        "envelope_version": 1,
        "kdf": "argon2id",
        "memory_kib": 65536,
        "iterations": 3,
        "parallelism": 1,
        "salt": base64.b64encode(b"s" * 16).decode(),
        "wrapped_dek": base64.b64encode(b"w" * 48).decode(),
        "wrapping_iv": base64.b64encode(b"n" * 12).decode(),
        "ciphertext": base64.b64encode(b"c" * 17).decode(),
        "image_iv": base64.b64encode(b"i" * 12).decode(),
        "mime": "image/png",
    }
    assert SignatureEnvelopeInput.model_validate(envelope).iterations == 3

    with pytest.raises(ValidationError):
        SignatureEnvelopeInput.model_validate({**envelope, "memory_kib": 2**30})
    with pytest.raises(ValidationError):
        SignatureEnvelopeInput.model_validate(
            {**envelope, "image_iv": envelope["wrapping_iv"]}
        )


def test_signature_envelope_rejects_noncanonical_or_wrong_size_base64() -> None:
    import base64

    envelope = {
        "envelope_version": 1,
        "kdf": "argon2id",
        "memory_kib": 65536,
        "iterations": 3,
        "parallelism": 1,
        "salt": base64.b64encode(b"s" * 16).decode(),
        "wrapped_dek": base64.b64encode(b"w" * 48).decode(),
        "wrapping_iv": base64.b64encode(b"n" * 12).decode(),
        "ciphertext": base64.b64encode(b"c" * 17).decode(),
        "image_iv": base64.b64encode(b"i" * 12).decode(),
        "mime": "image/png",
    }
    with pytest.raises(ValidationError):
        SignatureEnvelopeInput.model_validate({**envelope, "salt": "not-base64!"})
    with pytest.raises(ValidationError):
        SignatureEnvelopeInput.model_validate(
            {**envelope, "salt": f"{envelope['salt']} "}
        )
    with pytest.raises(ValidationError):
        SignatureEnvelopeInput.model_validate(
            {**envelope, "wrapped_dek": base64.b64encode(b"short").decode()}
        )
    with pytest.raises(ValidationError):
        SignatureEnvelopeInput.model_validate({**envelope, "user_id": "another-user"})
