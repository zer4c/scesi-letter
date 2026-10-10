import base64
import logging
import re
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.policy import SMTP
from uuid import uuid4

import httpx
from fastapi import HTTPException
from pymongo import AsyncMongoClient, ReturnDocument

from app.core.config import Settings
from app.modules.auth.documents import UserDocument
from app.modules.document.documents import DocumentVersionDocument, LetterDocument
from app.modules.document.storage import ArtifactStore
from app.modules.integration.crypto import decrypt_secret
from app.modules.integration.documents import (
    DriveArchiveMappingDocument,
    IntegrationConnectionDocument,
)
from app.modules.integration.services import GMAIL_SEND_SCOPE, GoogleConnectionService
from app.modules.mail.documents import (
    MailDispatchJobDocument,
    MailDispatchPayloadDocument,
)
from app.modules.mail.schemas import MailDispatchRequest
from app.modules.mail.services import MailDispatchService

LOGGER = logging.getLogger(__name__)
GOOGLE_GMAIL_MESSAGES_ENDPOINT = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
MAIL_TIMEOUT_SECONDS = 20
MAIL_LEASE = timedelta(minutes=2)
PDF_MAX_BYTES = 18_000_000
LETTER_IDENTIFIER = re.compile(r"(?:INV|SOL|MEM|ACT|PRES|CIRC|NOT|GEN)-SCESI-\d{4}-\d{3,}\Z")


def build_gmail_raw_message(
    *, from_address: str, payload: MailDispatchRequest, pdf_bytes: bytes, filename: str
) -> str:
    if len(pdf_bytes) > PDF_MAX_BYTES or not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("PDF artifact is invalid")
    message = EmailMessage(policy=SMTP)
    message["From"] = from_address
    message["To"] = ", ".join(str(email) for email in payload.to)
    if payload.cc:
        message["Cc"] = ", ".join(str(email) for email in payload.cc)
    if payload.bcc:
        message["Bcc"] = ", ".join(str(email) for email in payload.bcc)
    message["Subject"] = payload.subject
    message.set_content(payload.body, charset="utf-8")
    message.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=filename,
    )
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii").rstrip("=")


async def send_gmail_message(
    access_token: str,
    raw_message: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[str, str | None]:
    try:
        async with httpx.AsyncClient(
            transport=transport,
            follow_redirects=False,
            timeout=MAIL_TIMEOUT_SECONDS,
        ) as http:
            response = await http.post(
                GOOGLE_GMAIL_MESSAGES_ENDPOINT,
                headers={"Authorization": f"Bearer {access_token}"},
                json={"raw": raw_message},
            )
    except httpx.RequestError:
        return "unknown", "GMAIL_OUTCOME_UNKNOWN"
    if response.status_code >= 500:
        return "unknown", "GMAIL_OUTCOME_UNKNOWN"
    if response.status_code in {401, 403}:
        return "failed", "GMAIL_REAUTH_REQUIRED"
    if response.status_code != 200:
        return "failed", "GMAIL_REQUEST_REJECTED"
    try:
        message_id = response.json().get("id")
    except (ValueError, AttributeError):
        message_id = None
    if not isinstance(message_id, str) or not message_id:
        return "unknown", "GMAIL_OUTCOME_UNKNOWN"
    return "succeeded", None


class MailDispatchWorker:
    def __init__(
        self,
        settings: Settings,
        client: AsyncMongoClient,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        self._transport = transport
        self._worker_id = uuid4().hex
        self._store = ArtifactStore(settings.ARTIFACT_ROOT)
        self._connections = GoogleConnectionService(settings, transport)

    async def run_once(self) -> bool:
        await self._expire_uncertain_jobs()
        job = await self._claim_job()
        if job is None:
            return False
        try:
            await self._send(job)
        except HTTPException as error:
            code = {
                "GOOGLE_REAUTH_REQUIRED": "GMAIL_REAUTH_REQUIRED",
                "INTEGRATION_KEY_UNAVAILABLE": "INTEGRATION_KEY_UNAVAILABLE",
            }.get(str(error.detail), "GMAIL_CONNECTION_UNAVAILABLE")
            await self._finish(job, "failed", code)
            LOGGER.warning("Mail dispatch unavailable job_id=%s code=%s", job.id, code)
        except (FileNotFoundError, OSError, ValueError):
            await self._finish(job, "failed", "PDF_ARTIFACT_UNAVAILABLE")
            LOGGER.warning("Mail dispatch artifact unavailable job_id=%s", job.id)
        except Exception:
            await self._finish(job, "failed", "MAIL_DISPATCH_FAILED")
            LOGGER.exception("Mail dispatch failed before provider response job_id=%s", job.id)
        return True

    async def _claim_job(self) -> MailDispatchJobDocument | None:
        now = datetime.now(UTC)
        raw = await MailDispatchJobDocument.get_pymongo_collection().find_one_and_update(
            {"status": "queued"},
            {
                "$set": {"status": "running", "lease_owner": self._worker_id,
                         "lease_until": now + MAIL_LEASE, "updated_at": now},
                "$inc": {"attempt": 1},
            },
            sort=[("created_at", 1)],
            return_document=ReturnDocument.AFTER,
        )
        return MailDispatchJobDocument.model_validate(raw) if raw else None

    async def _expire_uncertain_jobs(self) -> None:
        now = datetime.now(UTC)
        await MailDispatchJobDocument.get_pymongo_collection().update_many(
            {"status": "running", "lease_until": {"$lte": now}},
            {"$set": {"status": "unknown", "error_code": "GMAIL_OUTCOME_UNKNOWN",
                      "lease_owner": None, "lease_until": None, "updated_at": now}},
        )

    async def _send(self, job: MailDispatchJobDocument) -> None:
        payload_record = await MailDispatchPayloadDocument.find_one(
            MailDispatchPayloadDocument.job_id == job.id,
            MailDispatchPayloadDocument.user_id == job.user_id,
        )
        if payload_record is None:
            await self._finish(job, "failed", "MAIL_PAYLOAD_EXPIRED")
            return
        raw_payload = decrypt_secret(
            payload_record.encrypted_payload,
            MailDispatchService._payload_aad(job.id, job.user_id),
            self._settings,
        )
        payload = MailDispatchRequest.model_validate_json(raw_payload)
        document = await LetterDocument.find_one(LetterDocument.id == job.document_id)
        version = await DocumentVersionDocument.find_one(
            DocumentVersionDocument.id == job.version_id,
            DocumentVersionDocument.document_id == job.document_id,
        )
        mapping = await DriveArchiveMappingDocument.find_one(
            DriveArchiveMappingDocument.version_id == job.version_id,
            DriveArchiveMappingDocument.status == "archived",
        )
        if (
            document is None
            or document.identifier is None
            or not LETTER_IDENTIFIER.fullmatch(document.identifier)
            or version is None
            or document.finalized_version_id != version.id
            or version.finalized_at is None
            or version.status != "archived"
            or version.pdf_hash != job.pdf_hash
            or mapping is None
            or mapping.document_id != document.id
            or mapping.pdf_hash != job.pdf_hash
            or not mapping.pdf_file_id
        ):
            await self._finish(job, "failed", "VERSION_NOT_SENDABLE")
            return
        connection = await IntegrationConnectionDocument.find_one(
            IntegrationConnectionDocument.id == job.connection_id,
            IntegrationConnectionDocument.kind == "gmail",
        )
        if connection is None:
            await self._finish(job, "failed", "GMAIL_CONNECTION_UNAVAILABLE")
            return
        if GMAIL_SEND_SCOPE not in connection.scopes:
            await self._finish(job, "failed", "GOOGLE_SCOPE_MISMATCH")
            return
        actor = await UserDocument.find_one(
            UserDocument.id == job.user_id,
            UserDocument.active == True,
        )
        if actor is None:
            await self._finish(job, "failed", "SENDER_UNAVAILABLE")
            return
        if connection.mode == "personal":
            if connection.owner_user_id != job.user_id:
                await self._finish(job, "failed", "GMAIL_CONNECTION_UNAVAILABLE")
                return
        elif connection.mode != "institutional" or connection.owner_user_id is not None:
            await self._finish(job, "failed", "GMAIL_CONNECTION_UNAVAILABLE")
            return
        access_token = await self._connections.get_access_token(
            connection, actor if connection.mode == "personal" else None
        )
        pdf_bytes = self._store.read_verified(
            document.id, version.id, "letter.pdf", job.pdf_hash
        )
        filename = f"{document.identifier}-v{version.version_number:04d}.pdf"
        raw_message = build_gmail_raw_message(
            from_address=str(connection.google_account),
            payload=payload,
            pdf_bytes=pdf_bytes,
            filename=filename,
        )

        now = datetime.now(UTC)
        marked = await MailDispatchJobDocument.get_pymongo_collection().update_one(
            {"_id": job.id, "status": "running", "lease_owner": self._worker_id},
            {"$set": {"submission_started_at": now, "lease_until": now + MAIL_LEASE,
                      "updated_at": now}},
        )
        if marked.matched_count != 1:
            return
        result, error_code = await send_gmail_message(
            access_token, raw_message, self._transport
        )
        if error_code == "GMAIL_REAUTH_REQUIRED":
            await self._connections._mark_reauthorization(connection)
        await self._finish(job, result, error_code)
        await payload_record.delete()

    async def _finish(
        self,
        job: MailDispatchJobDocument,
        status: str,
        error_code: str | None,
    ) -> None:
        await MailDispatchJobDocument.get_pymongo_collection().update_one(
            {"_id": job.id, "status": "running", "lease_owner": self._worker_id},
            {"$set": {"status": status, "error_code": error_code,
                      "lease_owner": None,
                      "lease_until": None, "updated_at": datetime.now(UTC)}},
        )
