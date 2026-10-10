import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from uuid import UUID

from fastapi import HTTPException, WebSocket
from pycrdt import (
    Decoder,
    Doc,
    Map,
    Text,
    YMessageType,
    YSyncMessageType,
    create_sync_message,
    create_update_message,
    handle_sync_message,
)
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError

from app.modules.auth.documents import UserDocument
from app.modules.automation.documents import LetterSuggestionDocument
from app.modules.collaboration.repositories import (
    CollaborationRepository,
    CollaborationRevisionConflict,
)
from app.modules.contact.documents import ContactDocument
from app.modules.document.documents import LetterDocument
from app.modules.document.schemas import LetterMetadata
from app.modules.document.services import DocumentService, calculate_source_hash

MAX_FRAME_BYTES = 1024 * 1024
MAX_DOCUMENT_BODY = 100_000
MAX_ROOM_CLIENTS = 10
MAX_DOCUMENT_METADATA_BYTES = 16_384
CHECKPOINT_IDLE_SECONDS = 2.0
CHECKPOINT_MAX_DELAY_SECONDS = 10.0
LOGGER = logging.getLogger(__name__)


class InvalidCollaborationMessage(ValueError):
    pass


@dataclass
class CollaborationRoom:
    document: LetterDocument
    ydoc: Doc
    last_sequence: int
    clients: set[WebSocket] = field(default_factory=set)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    checkpoint_task: asyncio.Task | None = None
    checkpoint_started_at: float | None = None
    checkpoint_changed_at: float | None = None
    checkpoint_actor_id: UUID | None = None


class CollaborationService:
    def __init__(self, client: AsyncMongoClient) -> None:
        self._client = client
        self._repository = CollaborationRepository()
        self._rooms: dict[UUID, CollaborationRoom] = {}
        self._rooms_lock = asyncio.Lock()

    async def open_room(self, document: LetterDocument) -> CollaborationRoom:
        async with self._rooms_lock:
            room = self._rooms.get(document.id)
            if room is not None:
                room.document = document
                return room

            initial = self._new_document(document)
            state, updates = await self._repository.load_state(
                document.id,
                initial.get_update(),
                initial.get_state(),
            )
            ydoc = self._empty_document()
            ydoc.apply_update(state.crdt_snapshot)
            for update in updates:
                ydoc.apply_update(update.binary_update)
            if ydoc.get_state() != state.state_vector and not updates:
                raise RuntimeError("Collaboration state vector is inconsistent")
            room = CollaborationRoom(
                document=document,
                ydoc=ydoc,
                last_sequence=state.last_sequence,
            )
            self._rooms[document.id] = room
            return room

    async def checkpoint_now(self, document_id: UUID, actor: UserDocument) -> None:
        room = self._rooms.get(document_id)
        if room is None:
            return
        async with room.lock:
            snapshot = self._empty_document()
            snapshot.apply_update(room.ydoc.get_update())
        await DocumentService().checkpoint_collaborative(
            document_id,
            self._parse_metadata(snapshot),
            str(snapshot["body"]),
            actor,
            self._client,
        )

    async def apply_suggestion(
        self,
        document: LetterDocument,
        suggestion: LetterSuggestionDocument,
        expected_source_hash: str,
        contact_id: UUID | None,
        actor: UserDocument,
    ) -> None:
        room = await self.open_room(document)
        async with room.lock:
            candidate = self._empty_document()
            candidate.apply_update(room.ydoc.get_update())
            current_metadata = self._parse_metadata(candidate).model_copy(
                update={
                    "identifier": document.identifier,
                    "template_revision": document.metadata.template_revision,
                }
            )
            body = str(candidate["body"])
            _, current_hash = calculate_source_hash(current_metadata, body)
            if (
                current_hash != expected_source_hash
                or suggestion.source_hash != expected_source_hash
                or suggestion.status != "proposed"
            ):
                raise HTTPException(status_code=409, detail="STALE_SUGGESTION")

            if suggestion.kind in {"grammar", "style", "reference"}:
                start, end = suggestion.start, suggestion.end
                if (
                    start is None
                    or end is None
                    or suggestion.original is None
                    or suggestion.replacement is None
                    or start < 0
                    or end <= start
                    or body[start:end] != suggestion.original
                ):
                    raise HTTPException(status_code=409, detail="STALE_SUGGESTION")
                # pycrdt mutation slices use UTF-8 byte offsets even though
                # suggestion offsets and Python string slices use code points.
                utf8_start = len(body[:start].encode("utf-8"))
                utf8_end = len(body[:end].encode("utf-8"))
                candidate["body"][utf8_start:utf8_end] = suggestion.replacement
            elif suggestion.kind == "document_type":
                if (
                    suggestion.field != "document_type"
                    or suggestion.replacement is None
                    or document.identifier is not None
                ):
                    raise HTTPException(
                        status_code=409, detail="SUGGESTION_NOT_APPLICABLE"
                    )
                candidate["metadata"]["document_type"] = suggestion.replacement
            elif suggestion.kind == "topic":
                if suggestion.field != "topic" or suggestion.replacement is None:
                    raise HTTPException(
                        status_code=409, detail="SUGGESTION_NOT_APPLICABLE"
                    )
                candidate["metadata"]["topic"] = suggestion.replacement
            elif suggestion.kind == "recipient_role":
                if (
                    suggestion.field != "recipient_role"
                    or suggestion.replacement is None
                    or contact_id is None
                ):
                    raise HTTPException(
                        status_code=422, detail="CONTACT_SELECTION_REQUIRED"
                    )
                contact = await ContactDocument.find_one(
                    ContactDocument.id == contact_id,
                    ContactDocument.active == True,  # noqa: E712
                )
                if contact is None or contact.role_key != suggestion.replacement:
                    raise HTTPException(status_code=409, detail="CONTACT_NOT_AVAILABLE")
                recipient = {
                    "name": contact.name,
                    "role": contact.role_label,
                    "institution": contact.institution,
                    "career": contact.career,
                    "email": contact.emails[0] if contact.emails else None,
                }
                candidate["metadata"]["recipient"] = json.dumps(
                    recipient, ensure_ascii=False, separators=(",", ":")
                )
                candidate["metadata"]["recipient_contact_id"] = str(contact.id)
            else:
                raise HTTPException(status_code=409, detail="SUGGESTION_NOT_APPLICABLE")

            self._validate_document_state(document, candidate)
            update = candidate.get_update(room.ydoc.get_state())
            if update == b"\x00\x00":
                raise HTTPException(status_code=409, detail="SUGGESTION_NO_CHANGE")
            try:
                sequence = await self._repository.append_suggestion_update(
                    document_id=document.id,
                    suggestion_id=suggestion.id,
                    expected_source_hash=expected_source_hash,
                    expected_sequence=room.last_sequence,
                    update=update,
                    snapshot=candidate.get_update(),
                    state_vector=candidate.get_state(),
                    client=self._client,
                )
            except CollaborationRevisionConflict as error:
                raise HTTPException(
                    status_code=409, detail="STALE_SUGGESTION"
                ) from error
            except PyMongoError as error:
                if error.has_error_label("TransientTransactionError") or getattr(
                    error, "code", None
                ) in {112, 251, 11000}:
                    raise HTTPException(
                        status_code=409, detail="STALE_SUGGESTION"
                    ) from error
                raise
            room.ydoc.apply_update(update)
            room.last_sequence = sequence
            self._schedule_checkpoint(room, actor.id)
            await self._broadcast_locked(room, create_update_message(update))

    async def add_client(
        self,
        room: CollaborationRoom,
        websocket: WebSocket,
    ) -> None:
        async with room.lock:
            if len(room.clients) >= MAX_ROOM_CLIENTS:
                raise InvalidCollaborationMessage("Room capacity reached")
            room.clients.add(websocket)
            await websocket.send_bytes(create_sync_message(room.ydoc))

    async def remove_client(
        self,
        document_id: UUID,
        room: CollaborationRoom,
        websocket: WebSocket,
    ) -> None:
        async with room.lock:
            room.clients.discard(websocket)
        if not room.clients:
            async with self._rooms_lock:
                if self._rooms.get(document_id) is room:
                    self._rooms.pop(document_id, None)

    async def process_message(
        self,
        room: CollaborationRoom,
        websocket: WebSocket,
        message: bytes,
        actor: UserDocument,
    ) -> None:
        if not message or len(message) > MAX_FRAME_BYTES:
            raise InvalidCollaborationMessage("Frame size is invalid")

        try:
            message_type = YMessageType(message[0])
        except ValueError as error:
            raise InvalidCollaborationMessage("Message type is invalid") from error

        if message_type == YMessageType.AWARENESS:
            try:
                if not Decoder(message[1:]).read_message():
                    raise ValueError("Awareness payload is empty")
            except Exception as error:
                raise InvalidCollaborationMessage(
                    "Awareness message is malformed"
                ) from error
            await self._broadcast(room, message)
            return
        if message_type != YMessageType.SYNC:
            raise InvalidCollaborationMessage("Message type is unsupported")

        async with room.lock:
            candidate = self._empty_document()
            candidate.apply_update(room.ydoc.get_update())
            try:
                decoder = Decoder(message[1:])
                subtype = YSyncMessageType(decoder.read_var_uint())
                reply = handle_sync_message(message[1:], candidate)
            except Exception as error:
                raise InvalidCollaborationMessage(
                    "Sync message is malformed"
                ) from error

            update = candidate.get_update(room.ydoc.get_state())
            if update != b"\x00\x00":
                self._validate_document_state(room.document, candidate)
                sequence = await self._repository.append_update(
                    room.document.id,
                    update,
                    candidate.get_update(),
                    candidate.get_state(),
                    self._client,
                )
                room.ydoc.apply_update(update)
                room.last_sequence = sequence
                self._schedule_checkpoint(room, actor.id)
                await self._broadcast_locked(room, create_update_message(update))

            if reply is not None:
                await websocket.send_bytes(reply)
            elif subtype == YSyncMessageType.SYNC_STEP1:
                await websocket.send_bytes(create_sync_message(room.ydoc))

    async def _broadcast(self, room: CollaborationRoom, message: bytes) -> None:
        async with room.lock:
            await self._broadcast_locked(room, message)

    @staticmethod
    async def _broadcast_locked(room: CollaborationRoom, message: bytes) -> None:
        clients = tuple(room.clients)
        if not clients:
            return
        results = await asyncio.gather(
            *(client.send_bytes(message) for client in clients),
            return_exceptions=True,
        )
        for client, result in zip(clients, results, strict=True):
            if isinstance(result, Exception):
                room.clients.discard(client)
                try:
                    await client.close(code=1011)
                except Exception:
                    pass

    @staticmethod
    def _new_document(document: LetterDocument) -> Doc:
        ydoc = CollaborationService._empty_document()
        ydoc["body"] = Text(document.body)
        metadata = document.metadata.model_dump(mode="json")
        for key in ("recipient", "sender"):
            if metadata.get(key) is not None:
                metadata[key] = json.dumps(
                    metadata[key], ensure_ascii=False, separators=(",", ":")
                )
        ydoc["metadata"] = Map(metadata)
        return ydoc

    @staticmethod
    def _empty_document() -> Doc:
        ydoc = Doc()
        ydoc["body"] = Text()
        ydoc["metadata"] = Map()
        return ydoc

    def _schedule_checkpoint(self, room: CollaborationRoom, actor_id: UUID) -> None:
        now = time.monotonic()
        room.checkpoint_changed_at = now
        room.checkpoint_actor_id = actor_id
        if room.checkpoint_task is None:
            room.checkpoint_started_at = now
            room.checkpoint_task = asyncio.create_task(
                self._checkpoint_after_quiet_period(room)
            )

    async def _checkpoint_after_quiet_period(self, room: CollaborationRoom) -> None:
        checkpointed_at = room.checkpoint_started_at or time.monotonic()
        try:
            while True:
                await asyncio.sleep(0.1)
                now = time.monotonic()
                changed_at = room.checkpoint_changed_at or checkpointed_at
                if (
                    now - changed_at >= CHECKPOINT_IDLE_SECONDS
                    or now - checkpointed_at >= CHECKPOINT_MAX_DELAY_SECONDS
                ):
                    break

            async with room.lock:
                snapshot = self._empty_document()
                snapshot.apply_update(room.ydoc.get_update())
                actor_id = room.checkpoint_actor_id
                checkpointed_at = room.checkpoint_changed_at or checkpointed_at
            if actor_id is None:
                return

            actor = await UserDocument.find_one(UserDocument.id == actor_id)
            if actor is None or not actor.active:
                return
            metadata = self._parse_metadata(snapshot)
            body = str(snapshot["body"])
            await DocumentService().checkpoint_collaborative(
                room.document.id,
                metadata,
                body,
                actor,
                self._client,
            )
        except Exception as error:
            LOGGER.warning(
                "Collaborative checkpoint failed document_id=%s error=%s",
                room.document.id,
                error.__class__.__name__,
            )
        finally:
            room.checkpoint_task = None
            room.checkpoint_started_at = None
            if (
                room.checkpoint_changed_at is not None
                and room.checkpoint_changed_at > checkpointed_at
            ):
                actor_id = room.checkpoint_actor_id
                if actor_id is not None:
                    self._schedule_checkpoint(room, actor_id)

    @staticmethod
    def _validate_document_state(document: LetterDocument, ydoc: Doc) -> None:
        try:
            body = str(ydoc["body"])
            raw_metadata = CollaborationService._parse_metadata(ydoc).model_dump(
                mode="json"
            )
            encoded_metadata = json.dumps(
                raw_metadata,
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
            if len(encoded_metadata) > MAX_DOCUMENT_METADATA_BYTES:
                raise InvalidCollaborationMessage("Metadata limit exceeded")
            metadata = LetterMetadata.model_validate(raw_metadata)
        except InvalidCollaborationMessage:
            raise
        except Exception as error:
            raise InvalidCollaborationMessage("Document metadata is invalid") from error

        if len(body) > MAX_DOCUMENT_BODY:
            raise InvalidCollaborationMessage("Document body limit exceeded")
        if document.identifier is not None and (
            metadata.identifier not in {None, document.identifier}
            or metadata.document_type != document.document_type
        ):
            raise InvalidCollaborationMessage("Numbered document identity is locked")
        if document.identifier is None and metadata.identifier is not None:
            raise InvalidCollaborationMessage("Document identifier is server-managed")
        if metadata.template_revision != document.metadata.template_revision:
            raise InvalidCollaborationMessage("Template revision is server-managed")

    @staticmethod
    def _parse_metadata(ydoc: Doc) -> LetterMetadata:
        raw_metadata = dict(ydoc["metadata"])
        for key in ("recipient", "sender"):
            partial_party = {}
            for field_name in ("name", "role", "institution", "career", "email"):
                map_key = f"{key}_{field_name}"
                if map_key in raw_metadata:
                    partial_party[field_name] = raw_metadata.pop(map_key)
            if partial_party:
                raw_metadata[key] = (
                    partial_party if partial_party.get("name", "").strip() else None
                )
            value = raw_metadata.get(key)
            if isinstance(value, str):
                raw_metadata[key] = json.loads(value)
        return LetterMetadata.model_validate(raw_metadata)
