from datetime import UTC, datetime
import hashlib
from uuid import UUID

from pymongo import AsyncMongoClient
from pymongo.errors import DuplicateKeyError

from app.core.database import transaction
from app.modules.collaboration.documents import (
    CollaborationUpdateDocument,
    DocumentStateDocument,
)


SNAPSHOT_INTERVAL = 100


class CollaborationRepository:
    async def load_state(
        self,
        document_id: UUID,
        initial_snapshot: bytes,
        initial_state_vector: bytes,
    ) -> tuple[DocumentStateDocument, list[CollaborationUpdateDocument]]:
        state = await DocumentStateDocument.find_one(
            DocumentStateDocument.document_id == document_id
        )
        if state is None:
            state = DocumentStateDocument(
                document_id=document_id,
                crdt_snapshot=initial_snapshot,
                state_vector=initial_state_vector,
                checkpoint_hash=hashlib.sha256(initial_snapshot).hexdigest(),
            )
            try:
                await state.insert()
            except DuplicateKeyError:
                state = await DocumentStateDocument.find_one(
                    DocumentStateDocument.document_id == document_id
                )
                if state is None:
                    raise

        if hashlib.sha256(state.crdt_snapshot).hexdigest() != state.checkpoint_hash:
            raise RuntimeError("Collaboration snapshot integrity check failed")

        updates = await CollaborationUpdateDocument.find(
            CollaborationUpdateDocument.document_id == document_id,
            CollaborationUpdateDocument.sequence > state.snapshot_sequence,
        ).sort(+CollaborationUpdateDocument.sequence).to_list()
        if len(updates) != state.last_sequence - state.snapshot_sequence:
            raise RuntimeError("Collaboration update log is incomplete")
        return state, updates

    async def append_update(
        self,
        document_id: UUID,
        update: bytes,
        snapshot: bytes,
        state_vector: bytes,
        client: AsyncMongoClient,
    ) -> int:
        now = datetime.now(UTC)
        async with transaction(client) as session:
            state = await DocumentStateDocument.find_one(
                DocumentStateDocument.document_id == document_id,
                session=session,
            )
            if state is None:
                raise RuntimeError("Collaboration state was not initialized")
            sequence = state.last_sequence + 1
            state.last_sequence = sequence
            state.server_revision += 1
            state.updated_at = now
            await CollaborationUpdateDocument(
                document_id=document_id,
                sequence=sequence,
                binary_update=update,
                created_at=now,
            ).insert(session=session)
            if sequence - state.snapshot_sequence >= SNAPSHOT_INTERVAL:
                state.crdt_snapshot = snapshot
                state.state_vector = state_vector
                state.checkpoint_hash = hashlib.sha256(snapshot).hexdigest()
                state.snapshot_sequence = sequence
                await CollaborationUpdateDocument.find(
                    CollaborationUpdateDocument.document_id == document_id,
                    CollaborationUpdateDocument.sequence <= sequence,
                    session=session,
                ).delete()
            await state.save(session=session)
            return sequence
