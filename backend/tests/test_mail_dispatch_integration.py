import asyncio
import base64
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from email import message_from_bytes
from email.policy import default
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from pymongo import AsyncMongoClient

from app.core.config import Settings
from app.core.database import initialize_persistence
from app.modules.auth.documents import UserDocument
from app.modules.document.documents import DocumentVersionDocument, LetterDocument
from app.modules.document.schemas import LetterMetadata
from app.modules.document.storage import ArtifactStore
from app.modules.integration.documents import (
    DriveArchiveMappingDocument,
    IntegrationConnectionDocument,
)
from app.modules.integration.services import GoogleConnectionService
from app.modules.mail.documents import (
    MailDispatchJobDocument,
    MailDispatchPayloadDocument,
)
from app.modules.mail.schemas import MailDispatchRequest
from app.modules.mail.services import MailDispatchService
from app.modules.mail.worker import MailDispatchWorker


def test_mail_jobs_are_idempotent_pdf_only_and_timeouts_are_not_retried(tmp_path):
    if os.environ.get("RUN_MONGODB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_MONGODB_INTEGRATION_TESTS=1 to run the isolated MongoDB test")

    async def exercise():
        database_name = f"scesi_t21_{uuid4().hex}"
        env_file = Path(__file__).resolve().parents[2] / ".env.example"
        settings = Settings(
            _env_file=env_file,
            MONGODB_DATABASE=database_name,
            INTEGRATION_ENCRYPTION_KEY=SecretStr(base64.b64encode(b"m" * 32).decode()),
            ARTIFACT_ROOT=tmp_path / "artifacts",
        )
        client = AsyncMongoClient(
            settings.MONGODB_URI.get_secret_value(),
            uuidRepresentation="standard",
            tz_aware=True,
        )
        try:
            await initialize_persistence(client[database_name])
            actor = UserDocument(
                normalized_email=f"{uuid4().hex}@example.test",
                display_name="Synthetic Mail Sender",
                password_hash="synthetic-password-hash",
            )
            await actor.insert()

            now = datetime.now(UTC)
            metadata = LetterMetadata(
                identifier="SOL-SCESI-2026-001",
                document_type="SOL",
                date="2026-10-10",
                template_revision=1,
            )
            document_id, version_id = uuid4(), uuid4()
            pdf_bytes = b"%PDF-1.7\nsynthetic test PDF"
            pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()
            md_hash = "a" * 64
            document = LetterDocument(
                id=document_id,
                owner_id=actor.id,
                document_type="SOL",
                identifier=metadata.identifier,
                identifier_year=2026,
                metadata=metadata,
                body="Synthetic body",
                draft_revision=2,
                source_hash="b" * 64,
                current_version=version_id,
                latest_version_number=1,
                finalized_version_id=version_id,
            )
            await document.insert()
            version = DocumentVersionDocument(
                id=version_id,
                document_id=document.id,
                version_number=1,
                metadata_snapshot=metadata,
                body_snapshot="Synthetic body",
                markdown_snapshot="---\nsynthetic: true\n---\nSynthetic body",
                template_revision=1,
                source_hash="b" * 64,
                md_hash=md_hash,
                pdf_hash=pdf_hash,
                status="archived",
                finalized_at=now,
                created_by=actor.id,
            )
            await version.insert()
            connection_id = uuid4()
            google_connections = GoogleConnectionService(settings)
            connection = IntegrationConnectionDocument(
                id=connection_id,
                kind="gmail",
                mode="personal",
                owner_user_id=actor.id,
                google_account="sender@example.com",
                encrypted_tokens=google_connections._encrypt_tokens(
                    {"access_token": "synthetic-access-token", "refresh_token": "synthetic-refresh-token"},
                    connection_id,
                    "gmail",
                    "personal",
                    actor.id,
                ),
                scopes=["openid", "email", "https://www.googleapis.com/auth/gmail.send"],
                expires_at=now + timedelta(hours=1),
            )
            await connection.insert()
            await DriveArchiveMappingDocument(
                document_id=document.id,
                version_id=version.id,
                connection_id=uuid4(),
                root_folder_id="synthetic-root",
                folder_ids=["synthetic-folder"],
                markdown_file_id="synthetic-markdown-id",
                pdf_file_id="synthetic-pdf-id",
                md_hash=md_hash,
                pdf_hash=pdf_hash,
                status="archived",
            ).insert()
            ArtifactStore(settings.ARTIFACT_ROOT).write_immutable(
                document.id, version.id, "letter.pdf", pdf_bytes, pdf_hash
            )

            request = MailDispatchRequest(
                document_id=document.id,
                version_id=version.id,
                connection_id=connection.id,
                to=["to@example.com"],
                cc=["copy@example.com"],
                bcc=["blind@example.com"],
                subject="Synthetic controlled message",
                body="Synthetic message body",
                confirmed=True,
            )
            service = MailDispatchService(settings)
            job = await service.enqueue(request, "integration-success", actor, client)
            repeated = await service.enqueue(request, "integration-success", actor, client)
            assert repeated.job_id == job.job_id

            provider_calls = 0

            def accepted_message(http_request):
                nonlocal provider_calls
                provider_calls += 1
                raw = http_request.read().decode("utf-8")
                payload = json.loads(raw)
                wire = base64.urlsafe_b64decode(payload["raw"] + "=" * (-len(payload["raw"]) % 4))
                message = message_from_bytes(wire, policy=default)
                assert message["Bcc"] == "blind@example.com"
                attachments = list(message.iter_attachments())
                assert len(attachments) == 1
                assert attachments[0].get_content_type() == "application/pdf"
                assert attachments[0].get_filename().endswith(".pdf")
                assert all(not part.get_filename().endswith(".md") for part in message.walk() if part.get_filename())
                return httpx.Response(200, json={"id": "synthetic-provider-message-id"})

            success_worker = MailDispatchWorker(settings, client, httpx.MockTransport(accepted_message))
            assert await success_worker.run_once()
            assert not await success_worker.run_once()
            succeeded = await MailDispatchJobDocument.find_one(MailDispatchJobDocument.id == job.job_id)
            assert succeeded and succeeded.status == "succeeded"
            assert provider_calls == 1
            assert await MailDispatchPayloadDocument.find_one(
                MailDispatchPayloadDocument.job_id == job.job_id
            ) is None

            timeout_request = request.model_copy(update={"subject": "Synthetic timeout case"})
            timeout_job = await service.enqueue(timeout_request, "integration-timeout", actor, client)
            timeout_calls = 0

            def timeout_message(_http_request):
                nonlocal timeout_calls
                timeout_calls += 1
                raise httpx.ReadTimeout("simulated provider response loss")

            timeout_worker = MailDispatchWorker(settings, client, httpx.MockTransport(timeout_message))
            assert await timeout_worker.run_once()
            assert not await timeout_worker.run_once()
            unknown = await MailDispatchJobDocument.find_one(MailDispatchJobDocument.id == timeout_job.job_id)
            assert unknown and unknown.status == "unknown"
            assert unknown.error_code == "GMAIL_OUTCOME_UNKNOWN"
            assert timeout_calls == 1
            await client[database_name].command("ping")
        finally:
            await client.drop_database(database_name)
            await client.close()

    asyncio.run(exercise())
