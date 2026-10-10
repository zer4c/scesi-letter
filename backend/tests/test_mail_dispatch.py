import asyncio
import base64
from email import message_from_bytes
from email.policy import default
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.modules.mail.schemas import MailDispatchRequest
from app.modules.mail.worker import build_gmail_raw_message, send_gmail_message


def mail_payload(**overrides):
    value = {
        "document_id": uuid4(),
        "version_id": uuid4(),
        "connection_id": uuid4(),
        "to": ["to@example.com"],
        "cc": ["copy@example.com"],
        "bcc": ["blind@example.com"],
        "subject": "Solicitud académica",
        "body": "Buenos días.\nAdjuntamos la carta.",
        "confirmed": True,
    }
    value.update(overrides)
    return MailDispatchRequest.model_validate(value)


def test_mail_requires_confirmation_and_valid_to_and_rejects_duplicate_recipients():
    with pytest.raises(ValidationError):
        mail_payload(confirmed=False)
    with pytest.raises(ValidationError):
        mail_payload(to=[])
    with pytest.raises(ValidationError):
        mail_payload(cc=["TO@example.test"])


def test_subject_cannot_inject_headers_and_body_preserves_new_lines():
    with pytest.raises(ValidationError):
        mail_payload(subject="Subject\nBcc: private@example.com")
    assert mail_payload(body="Line one\r\nLine two").body == "Line one\nLine two"


def test_gmail_mime_contains_bcc_and_pdf_but_never_markdown():
    payload = mail_payload()
    raw = build_gmail_raw_message(
        from_address="sender@example.com",
        payload=payload,
        pdf_bytes=b"%PDF-1.7\nfixture",
        filename="SOL-SCESI-2026-001-v0001.pdf",
    )
    wire = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    message = message_from_bytes(wire, policy=default)

    assert message["From"] == "sender@example.com"
    assert message["To"] == "to@example.com"
    assert message["Cc"] == "copy@example.com"
    assert message["Bcc"] == "blind@example.com"
    attachments = list(message.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_content_type() == "application/pdf"
    assert attachments[0].get_filename().endswith(".pdf")
    assert attachments[0].get_payload(decode=True) == b"%PDF-1.7\nfixture"
    assert all(not part.get_filename().endswith(".md") for part in message.walk() if part.get_filename())


def test_gmail_mime_rejects_non_pdf_or_oversized_artifacts():
    with pytest.raises(ValueError):
        build_gmail_raw_message(
            from_address="sender@example.com",
            payload=mail_payload(),
            pdf_bytes=b"not a PDF",
            filename="letter.pdf",
        )


def test_provider_timeout_is_unknown_and_never_retried():
    calls = 0

    def handler(_request):
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("simulated timeout")

    result = asyncio.run(send_gmail_message("synthetic-token", "synthetic-mime", httpx.MockTransport(handler)))

    assert result == ("unknown", "GMAIL_OUTCOME_UNKNOWN")
    assert calls == 1


def test_provider_success_and_rejection_are_distinguished_without_message_history():
    async def send(status, body):
        return await send_gmail_message(
            "synthetic-token",
            "synthetic-mime",
            httpx.MockTransport(lambda _request: httpx.Response(status, json=body)),
        )

    assert asyncio.run(send(200, {"id": "provider-id"})) == ("succeeded", None)
    assert asyncio.run(send(403, {"error": "scope"})) == ("failed", "GMAIL_REAUTH_REQUIRED")
    assert asyncio.run(send(503, {"error": "temporary"})) == ("unknown", "GMAIL_OUTCOME_UNKNOWN")
