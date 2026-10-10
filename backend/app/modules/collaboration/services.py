import asyncio
from dataclasses import dataclass, field
import json
import logging
import time
from uuid import UUID

from fastapi import WebSocket
from pymongo import AsyncMongoClient
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

from app.modules.auth.documents import UserDocument
from app.modules.collaboration.repositories import CollaborationRepository
from app.modules.document.documents import LetterDocument
from app.modules.document.schemas import LetterMetadata
from app.modules.document.services import DocumentService


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
                if len(room.clients) >= MAX_ROOM_CLIENTS:
                    raise InvalidCollaborationMessage("Room capacity reached")
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
                raise InvalidCollaborationMessage("Awareness message is malformed") from error
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
                raise InvalidCollaborationMessage("Sync message is malformed") from error

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

        if not body.strip() or len(body) > MAX_DOCUMENT_BODY:
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
            value = raw_metadata.get(key)
            if isinstance(value, str):
                raw_metadata[key] = json.loads(value)
        return LetterMetadata.model_validate(raw_metadata)
