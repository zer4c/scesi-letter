from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest
from pycrdt import Doc, Map

from app.main import app
from app.modules.auth.routes import require_current_user
from app.modules.collaboration.services import CollaborationService
from app.modules.document.schemas import DocumentCreate, LetterFields
from app.modules.event.services import EventService
from app.modules.signature.schemas import SignatureEnvelopeInput
from pydantic import ValidationError


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
    assert (
        "post"
        in paths["/api/documents/{document_id}/suggestions/{suggestion_id}/reject"]
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
