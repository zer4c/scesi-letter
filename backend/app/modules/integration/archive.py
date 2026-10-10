from datetime import UTC, datetime, timedelta
import hashlib
import json
import logging
import re
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException
from pymongo import AsyncMongoClient, ReturnDocument

from app.core.config import Settings
from app.core.database import transaction
from app.modules.document.documents import DocumentVersionDocument, LetterDocument
from app.modules.document.storage import ArtifactStore
from app.modules.event.documents import EventDocument
from app.modules.integration.documents import (
    DriveArchiveJobDocument,
    DriveArchiveMappingDocument,
    DriveFolderMappingDocument,
    IntegrationConnectionDocument,
)
from app.modules.integration.services import (
    GOOGLE_DRIVE_FILES_ENDPOINT,
    GoogleConnectionService,
)


LOGGER = logging.getLogger(__name__)
DRIVE_TIMEOUT = 20
LEASE = timedelta(minutes=3)
MAX_ATTEMPTS = 5
TYPE_TOPIC = {
    "INV": "invitations", "SOL": "requests", "MEM": "requests",
    "ACT": "activities", "PRES": "presentations", "CIRC": "notifications",
    "NOT": "notifications",
}
TOPIC_HINTS = (
    ("classrooms", ("aula", "aulas", "ambiente", "salon", "classroom", "room")),
    ("furniture", ("mobiliario", "mueble", "silla", "mesa", "furniture")),
    ("permissions", ("permiso", "autorizacion", "authorization", "permission")),
    ("presentations", ("exposicion", "presentacion", "presentation")),
    ("activities", ("actividad", "jornada", "feria", "activity", "event")),
    ("invitations", ("invitacion", "invitaciones", "invite", "invitation")),
    ("notifications", ("notificacion", "comunicado", "circular", "notification")),
)


class DriveArchiveError(Exception):
    def __init__(self, code: str, retryable: bool = False) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(code)


def _safe_segment(value: str) -> str:
    segment = re.sub(r"[^a-zA-Z0-9._ -]+", "-", value).strip(" .-")
    return (segment[:100] or "untitled")


def _category(job: DriveArchiveJobDocument, document: LetterDocument) -> str | None:
    if job.topic_category_override:
        return job.topic_category_override
    topic = (getattr(getattr(document, "metadata", None), "topic", None) or "").casefold()
    for category, words in TOPIC_HINTS:
        if any(word in topic for word in words):
            return category
    return TYPE_TOPIC.get(document.document_type)


class DriveAPI:
    def __init__(self, token: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._token = token
        self._transport = transport

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = f"Bearer {self._token}"
        async with httpx.AsyncClient(timeout=DRIVE_TIMEOUT, transport=self._transport) as client:
            try:
                response = await client.request(method, url, headers=headers, **kwargs)
            except httpx.TimeoutException as error:
                raise DriveArchiveError("DRIVE_TIMEOUT", retryable=True) from error
            except httpx.HTTPError as error:
                raise DriveArchiveError("DRIVE_UNAVAILABLE", retryable=True) from error
        if response.status_code in {401, 403}:
            raise DriveArchiveError("DRIVE_ACCESS_DENIED")
        if response.status_code >= 500 or response.status_code == 429:
            raise DriveArchiveError("DRIVE_UNAVAILABLE", retryable=True)
        return response

    async def find_by_property(self, key: str, value: str, parent_id: str | None = None):
        escaped = value.replace("'", "\\'")
        query = f"appProperties has {{ key='{key}' and value='{escaped}' }} and trashed=false"
        if parent_id:
            query += f" and '{parent_id}' in parents"
        response = await self._request(
            "GET", GOOGLE_DRIVE_FILES_ENDPOINT,
            params={"q": query, "fields": "files(id,name,mimeType,appProperties,parents,trashed)", "pageSize": 10},
        )
        if response.status_code >= 400:
            raise DriveArchiveError("DRIVE_LOOKUP_FAILED", retryable=response.status_code >= 500)
        return response.json().get("files", [])

    async def get_file(self, file_id: str):
        response = await self._request(
            "GET", f"{GOOGLE_DRIVE_FILES_ENDPOINT}/{file_id}",
            params={"fields": "id,trashed,appProperties,parents"},
        )
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise DriveArchiveError("DRIVE_LOOKUP_FAILED", retryable=response.status_code >= 500)
        result = response.json()
        return None if result.get("trashed") else result

    async def ensure_folder(self, root_id: str, parent_id: str, name: str, key: str) -> str:
        collection = DriveFolderMappingDocument.get_pymongo_collection()
        existing = await collection.find_one({"root_folder_id": root_id, "mapping_key": key})
        if existing and existing.get("status") == "ready" and existing.get("folder_id"):
            return existing["folder_id"]
        now = datetime.now(UTC)
        worker_id = uuid4().hex
        mapping = await collection.find_one_and_update(
            {"root_folder_id": root_id, "mapping_key": key,
             "$or": [{"lease_until": None}, {"lease_until": {"$lte": now}}]},
            {"$set": {"parent_folder_id": parent_id, "folder_name": name,
                      "status": "creating", "lease_owner": worker_id,
                      "lease_until": now + LEASE, "updated_at": now},
             "$setOnInsert": {"_id": uuid4(), "root_folder_id": root_id, "mapping_key": key}},
            upsert=True, return_document=ReturnDocument.AFTER,
        )
        if mapping.get("lease_owner") != worker_id:
            raise DriveArchiveError("DRIVE_FOLDER_BUSY", retryable=True)
        try:
            found = await self.find_by_property("scesi_folder_key", key)
            folder_id = found[0]["id"] if found else None
            if folder_id is None:
                metadata = {"name": name, "mimeType": "application/vnd.google-apps.folder",
                            "parents": [parent_id], "appProperties": {"scesi_folder_key": key}}
                response = await self._request("POST", GOOGLE_DRIVE_FILES_ENDPOINT,
                                               params={"fields": "id"}, json=metadata)
                if response.status_code >= 400:
                    raise DriveArchiveError("DRIVE_FOLDER_CREATE_FAILED", retryable=response.status_code >= 500)
                folder_id = response.json().get("id")
            if not folder_id:
                raise DriveArchiveError("DRIVE_FOLDER_CREATE_FAILED", retryable=True)
            await collection.update_one(
                {"_id": mapping["_id"], "lease_owner": worker_id},
                {"$set": {"folder_id": folder_id, "status": "ready", "lease_owner": None,
                          "lease_until": None, "updated_at": datetime.now(UTC)}},
            )
            return folder_id
        except DriveArchiveError as error:
            if error.code == "DRIVE_TIMEOUT":
                found = await self.find_by_property("scesi_folder_key", key)
                if found:
                    folder_id = found[0]["id"]
                    await collection.update_one(
                        {"_id": mapping["_id"], "lease_owner": worker_id},
                        {"$set": {"folder_id": folder_id, "status": "ready",
                                  "lease_owner": None, "lease_until": None,
                                  "updated_at": datetime.now(UTC)}},
                    )
                    return folder_id
            await collection.update_one({"_id": mapping["_id"], "lease_owner": worker_id},
                                        {"$set": {"lease_until": datetime.now(UTC), "lease_owner": None}})
            raise
        except Exception:
            await collection.update_one({"_id": mapping["_id"], "lease_owner": worker_id},
                                        {"$set": {"lease_until": datetime.now(UTC), "lease_owner": None}})
            raise

    async def upload_immutable(self, parent_id: str, name: str, kind: str, document_id: UUID, version_id: UUID,
                               content: bytes, digest: str) -> str:
        app_key = "scesi_artifact_key"
        app_value = f"{version_id}:{kind}:{digest}"
        found = await self.find_by_property(app_key, app_value, parent_id)
        if found:
            return found[0]["id"]
        metadata = json.dumps({"name": name, "parents": [parent_id],
                               "appProperties": {app_key: app_value, "scesi_document_id": str(document_id),
                                                 "scesi_version_id": str(version_id), "scesi_kind": kind,
                                                 "scesi_hash": digest}})
        mime = "text/markdown" if kind == "markdown" else "application/pdf"
        boundary = f"scesi-{uuid4().hex}"
        body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{metadata}\r\n"
                f"--{boundary}\r\nContent-Type: {mime}\r\n\r\n").encode() + content + f"\r\n--{boundary}--".encode()
        try:
            response = await self._request("POST", f"{GOOGLE_DRIVE_FILES_ENDPOINT}?uploadType=multipart&fields=id",
                headers={"Content-Type": f"multipart/related; boundary={boundary}"}, content=body)
        except DriveArchiveError as error:
            if error.code == "DRIVE_TIMEOUT":
                found = await self.find_by_property(app_key, app_value, parent_id)
                if found:
                    return found[0]["id"]
            raise
        if response.status_code >= 400:
            raise DriveArchiveError("DRIVE_UPLOAD_FAILED", retryable=response.status_code >= 500)
        file_id = response.json().get("id")
        if not file_id:
            raise DriveArchiveError("DRIVE_UPLOAD_FAILED", retryable=True)
        return file_id


class DriveArchiveWorker:
    def __init__(self, settings: Settings, client: AsyncMongoClient,
                 connection_service: GoogleConnectionService | None = None,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._settings = settings
        self._client = client
        self._connections = connection_service or GoogleConnectionService(settings)
        self._transport = transport
        self._worker_id = uuid4().hex
        self._store = ArtifactStore(settings.ARTIFACT_ROOT)

    async def run_once(self) -> bool:
        now = datetime.now(UTC)
        active_connection = await IntegrationConnectionDocument.find_one(
            IntegrationConnectionDocument.kind == "drive",
            IntegrationConnectionDocument.mode == "institutional",
            IntegrationConnectionDocument.status == "active",
        )
        if active_connection and active_connection.root_folder_id:
            await DriveArchiveJobDocument.get_pymongo_collection().update_many(
                {"status": "waiting_connection"},
                {"$set": {"status": "queued", "error_code": None, "updated_at": now}},
            )
        raw = await DriveArchiveJobDocument.get_pymongo_collection().find_one_and_update(
            {"$or": [{"status": "queued"},
                     {"status": "retry_wait", "$or": [{"next_attempt_at": None},
                                                         {"next_attempt_at": {"$lte": now}}]},
                     {"status": "running", "lease_until": {"$lte": now}}]},
            {"$set": {"status": "running", "lease_owner": self._worker_id,
                      "lease_until": now + LEASE, "updated_at": now}, "$inc": {"attempt": 1}},
            sort=[("created_at", 1)], return_document=ReturnDocument.AFTER)
        if raw is None:
            return False
        job = DriveArchiveJobDocument.model_validate(raw)
        try:
            await self._archive(job)
        except DriveArchiveError as error:
            await self._fail(job, error.code, error.retryable)
            LOGGER.warning("Drive archive operation failed job_id=%s code=%s", job.id, error.code)
        except HTTPException as error:
            if error.detail == "GOOGLE_REAUTH_REQUIRED":
                await self._set_status(job, "waiting_connection", "DRIVE_REAUTH_REQUIRED")
            else:
                await self._fail(job, "DRIVE_CONNECTION_FAILED", False)
            LOGGER.warning("Drive connection unavailable job_id=%s", job.id)
        except Exception:
            await self._fail(job, "ARCHIVE_FAILED", True)
            LOGGER.exception("Drive archive operation failed job_id=%s", job.id)
        return True

    async def _archive(self, job: DriveArchiveJobDocument) -> None:
        version = await DocumentVersionDocument.find_one(DocumentVersionDocument.id == job.version_id)
        document = await LetterDocument.find_one(LetterDocument.id == job.document_id)
        if version is None or document is None or not document.identifier:
            raise DriveArchiveError("VERSION_UNAVAILABLE")
        if version.pdf_hash is None:
            raise DriveArchiveError("VERSION_NOT_RENDERED", retryable=True)
        category = _category(job, document)
        if category is None:
            await self._set_status(job, "needs_classification", "ARCHIVE_CLASSIFICATION_REQUIRED")
            return
        connection = await IntegrationConnectionDocument.find_one(
            IntegrationConnectionDocument.kind == "drive",
            IntegrationConnectionDocument.mode == "institutional",
            IntegrationConnectionDocument.status == "active",
        )
        if connection is None or not connection.root_folder_id:
            await self._set_status(job, "waiting_connection", "DRIVE_CONNECTION_REQUIRED")
            return
        token = await self._connections.get_access_token(connection, None)
        await DriveArchiveJobDocument.get_pymongo_collection().update_one(
            {"_id": job.id, "lease_owner": self._worker_id},
            {"$set": {"connection_id": connection.id, "root_folder_id": connection.root_folder_id}},
        )
        drive = DriveAPI(token, self._transport)
        root = connection.root_folder_id
        current = root
        year = str(document.identifier_year or version.metadata_snapshot.date.year)
        parts = [(year, f"year:{year}"), ("letters", "letters")]
        if version.metadata_snapshot.event_id:
            event = await EventDocument.find_one(EventDocument.id == version.metadata_snapshot.event_id)
            if event:
                parts.append(("events", "events"))
                parts.append((_safe_segment(event.slug), f"event:{event.id}"))
        parts.append((category, f"category:{category}"))
        key_parts = []
        for name, stable_key in parts:
            key_parts.append(stable_key)
            key = hashlib.sha256(f"{root}:{'/'.join(key_parts)}".encode()).hexdigest()
            current = await drive.ensure_folder(root, current, name, key)
        md_bytes = self._store.read_verified(document.id, version.id, "letter.md", version.md_hash)
        pdf_bytes = self._store.read_verified(document.id, version.id, "letter.pdf", version.pdf_hash)
        if len(md_bytes) > 2_000_000 or len(pdf_bytes) > 20_000_000:
            raise DriveArchiveError("ARCHIVE_FILE_TOO_LARGE")
        mapping = await DriveArchiveMappingDocument.find_one(
            DriveArchiveMappingDocument.version_id == version.id,
            DriveArchiveMappingDocument.root_folder_id == root,
        )
        if mapping and mapping.status == "archived":
            await self._validate_remote_file(drive, mapping.markdown_file_id,
                                            version.id, "markdown", version.md_hash)
            await self._validate_remote_file(drive, mapping.pdf_file_id,
                                            version.id, "pdf", version.pdf_hash)
            await self._set_status(job, "succeeded", None)
            return
        if mapping and mapping.markdown_file_id and mapping.md_hash != version.md_hash:
            raise DriveArchiveError("DRIVE_ARCHIVE_HASH_CONFLICT")
        if mapping and mapping.pdf_file_id and mapping.pdf_hash != version.pdf_hash:
            raise DriveArchiveError("DRIVE_ARCHIVE_HASH_CONFLICT")
        if mapping and mapping.markdown_file_id:
            await self._validate_remote_file(drive, mapping.markdown_file_id,
                                            version.id, "markdown", version.md_hash)
        if mapping and mapping.pdf_file_id:
            await self._validate_remote_file(drive, mapping.pdf_file_id,
                                            version.id, "pdf", version.pdf_hash)
        mapping = mapping or DriveArchiveMappingDocument(
            document_id=document.id, version_id=version.id, connection_id=connection.id,
            root_folder_id=root, md_hash=version.md_hash, pdf_hash=version.pdf_hash,
        )
        mapping.folder_ids = [current]
        mapping.connection_id = connection.id
        mapping.md_hash = version.md_hash
        mapping.pdf_hash = version.pdf_hash
        await mapping.save()
        base = document.identifier
        md_name = f"{base}-v{version.version_number:04d}.md"
        pdf_name = f"{base}-v{version.version_number:04d}.pdf"
        if not mapping.markdown_file_id:
            mapping.markdown_file_id = await drive.upload_immutable(
                current, md_name, "markdown", document.id, version.id, md_bytes, version.md_hash)
            await mapping.save()
        if not mapping.pdf_file_id:
            mapping.pdf_file_id = await drive.upload_immutable(
                current, pdf_name, "pdf", document.id, version.id, pdf_bytes, version.pdf_hash)
            await mapping.save()
        mapping.status = "archived"
        mapping.updated_at = datetime.now(UTC)
        async with transaction(self._client) as session:
            await mapping.save(session=session)
            current_version = await DocumentVersionDocument.find_one(
                DocumentVersionDocument.id == version.id, session=session)
            if current_version:
                current_version.status = "archived"
                await current_version.save(session=session)
            await self._finish_job(job, "succeeded", None, session)

    @staticmethod
    async def _validate_remote_file(drive: DriveAPI, file_id: str | None,
                                    version_id: UUID, kind: str, digest: str) -> None:
        if not file_id:
            raise DriveArchiveError("DRIVE_ARCHIVE_FILE_MISSING")
        remote = await drive.get_file(file_id)
        if remote is None:
            raise DriveArchiveError("DRIVE_ARCHIVE_FILE_MISSING")
        properties = remote.get("appProperties", {})
        expected = f"{version_id}:{kind}:{digest}"
        if (properties.get("scesi_artifact_key") != expected
                or properties.get("scesi_hash") != digest):
            raise DriveArchiveError("DRIVE_ARCHIVE_HASH_CONFLICT")

    async def _set_status(self, job: DriveArchiveJobDocument, status: str, code: str | None) -> None:
        collection = DriveArchiveJobDocument.get_pymongo_collection()
        await collection.update_one({"_id": job.id, "lease_owner": self._worker_id},
                                    {"$set": {"status": status, "error_code": code,
                                               "lease_owner": None, "lease_until": None,
                                               "updated_at": datetime.now(UTC)}})

    async def _finish_job(self, job, status: str, code: str | None, session) -> None:
        await DriveArchiveJobDocument.get_pymongo_collection().update_one(
            {"_id": job.id, "lease_owner": self._worker_id},
            {"$set": {"status": status, "error_code": code, "lease_owner": None,
                      "lease_until": None, "updated_at": datetime.now(UTC)}}, session=session)

    async def _fail(self, job: DriveArchiveJobDocument, code: str, retryable: bool) -> None:
        terminal = not retryable or job.attempt >= MAX_ATTEMPTS
        status = "failed" if terminal else "retry_wait"
        next_attempt = datetime.now(UTC) + timedelta(seconds=min(30 * 2 ** (job.attempt - 1), 900))
        await DriveArchiveJobDocument.get_pymongo_collection().update_one(
            {"_id": job.id, "lease_owner": self._worker_id},
            {"$set": {"status": status, "error_code": code, "lease_owner": None,
                      "lease_until": None, "next_attempt_at": None if terminal else next_attempt,
                      "updated_at": datetime.now(UTC)}})
        version = await DocumentVersionDocument.find_one(
            DocumentVersionDocument.id == job.version_id
        )
        if version is not None and version.status == "ready":
            version.status = "sync_failed"
            await version.save()
