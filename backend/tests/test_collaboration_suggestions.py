import asyncio
import os
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pymongo import AsyncMongoClient

from app.modules.collaboration.services import (
    CollaborationRoom,
    CollaborationService,
)
from app.modules.document.schemas import LetterMetadata
from app.modules.document.services import calculate_source_hash


def test_accept_applies_exact_unicode_codepoint_range_to_live_room():
    actor = SimpleNamespace(id=uuid4())
    metadata = LetterMetadata(
        document_type="SOL",
        date=date(2026, 10, 10),
        template_revision=1,
    )
    body = "Año🙂 solicita una sala."
    _, source_hash = calculate_source_hash(metadata, body)
    document = SimpleNamespace(
        id=uuid4(),
        document_type="SOL",
        identifier=None,
        metadata=metadata,
        body=body,
        source_hash=source_hash,
    )
    ydoc = CollaborationService._new_document(document)
    room = CollaborationRoom(document=document, ydoc=ydoc, last_sequence=0)
    service = CollaborationService(SimpleNamespace())
    service.open_room = AsyncMock(return_value=room)
    service._repository.append_suggestion_update = AsyncMock(return_value=1)
    service._schedule_checkpoint = Mock()
    suggestion = SimpleNamespace(
        id=uuid4(),
        document_id=document.id,
        source_hash=source_hash,
        status="proposed",
        kind="grammar",
        original="🙂",
        replacement="área",
        start=3,
        end=4,
        reason="La redacción puede ser más clara.",
    )

    asyncio.run(
        service.apply_suggestion(document, suggestion, source_hash, None, actor)
    )

    assert str(room.ydoc["body"]) == "Añoárea solicita una sala."
    service._repository.append_suggestion_update.assert_awaited_once()


def test_accept_rejects_changed_live_text_before_persisting_a_decision():
    actor = SimpleNamespace(id=uuid4())
    metadata = LetterMetadata(
        document_type="SOL",
        date=date(2026, 10, 10),
        template_revision=1,
    )
    body = "Solicito préstamo de aula."
    _, source_hash = calculate_source_hash(metadata, body)
    document = SimpleNamespace(
        id=uuid4(),
        document_type="SOL",
        identifier=None,
        metadata=metadata,
        body=body,
        source_hash=source_hash,
    )
    ydoc = CollaborationService._new_document(document)
    ydoc["body"][0:8] = "Pedimos"
    room = CollaborationRoom(document=document, ydoc=ydoc, last_sequence=1)
    service = CollaborationService(SimpleNamespace())
    service.open_room = AsyncMock(return_value=room)
    service._repository.append_suggestion_update = AsyncMock(return_value=2)
    service._schedule_checkpoint = Mock()
    suggestion = SimpleNamespace(
        id=uuid4(),
        document_id=document.id,
        source_hash=source_hash,
        status="proposed",
        kind="grammar",
        original="Solicito",
        replacement="Pido",
        start=0,
        end=8,
        reason="La redacción puede ser más clara.",
    )

    async def apply():
        await service.apply_suggestion(document, suggestion, source_hash, None, actor)

    with pytest.raises(HTTPException) as error:
        asyncio.run(apply())

    assert error.value.status_code == 409
    service._repository.append_suggestion_update.assert_not_awaited()


def test_mongodb_acceptance_is_atomic_under_concurrent_requests():
    if os.getenv("RUN_MONGODB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_MONGODB_INTEGRATION_TESTS=1 to use the local replica set")

    from app.core.config import Settings
    from app.core.database import initialize_persistence
    from app.modules.auth.documents import UserDocument
    from app.modules.automation.documents import LetterSuggestionDocument
    from app.modules.collaboration.documents import (
        CollaborationUpdateDocument,
        DocumentStateDocument,
    )
    from app.modules.document.documents import LetterDocument

    async def exercise():
        database_name = f"scesi_t18_{uuid4().hex}"
        env_file = Path(__file__).resolve().parents[2] / ".env.example"
        settings = Settings(_env_file=env_file, MONGODB_DATABASE=database_name)
        client = AsyncMongoClient(
            settings.MONGODB_URI.get_secret_value(),
            uuidRepresentation="standard",
            tz_aware=True,
        )
        try:
            await initialize_persistence(client[database_name])
            actor = UserDocument(
                normalized_email=f"{uuid4().hex}@example.test",
                display_name="Synthetic Reviewer",
                password_hash="synthetic-password-hash",
            )
            await actor.insert()
            metadata = LetterMetadata(
                document_type="SOL",
                date=date(2026, 10, 10),
                template_revision=1,
            )
            body = "Año🙂 solicita una sala."
            _, source_hash = calculate_source_hash(metadata, body)
            document = LetterDocument(
                owner_id=actor.id,
                document_type="SOL",
                metadata=metadata,
                body=body,
                source_hash=source_hash,
            )
            await document.insert()
            suggestion = LetterSuggestionDocument(
                document_id=document.id,
                source_hash=source_hash,
                kind="grammar",
                original="🙂",
                replacement="área",
                start=3,
                end=4,
                reason="La redacción puede ser más clara.",
            )
            await suggestion.insert()

            first = CollaborationService(client)
            second = CollaborationService(client)
            await first.open_room(document)
            await second.open_room(document)
            outcomes = await asyncio.gather(
                first.apply_suggestion(document, suggestion, source_hash, None, actor),
                second.apply_suggestion(document, suggestion, source_hash, None, actor),
                return_exceptions=True,
            )
            assert sum(not isinstance(result, Exception) for result in outcomes) == 1
            failures = [result for result in outcomes if isinstance(result, Exception)]
            assert len(failures) == 1
            assert isinstance(failures[0], HTTPException)
            assert failures[0].status_code == 409
            rooms = [first._rooms[document.id], second._rooms[document.id]]
            assert (
                sum(
                    str(room.ydoc["body"]) == "Añoárea solicita una sala."
                    for room in rooms
                )
                == 1
            )
            winner = next(
                service
                for service in (first, second)
                if str(service._rooms[document.id].ydoc["body"])
                == "Añoárea solicita una sala."
            )
            await winner.checkpoint_now(document.id, actor)
            updated_document = await LetterDocument.find_one(
                LetterDocument.id == document.id
            )
            assert updated_document is not None
            assert updated_document.body == "Añoárea solicita una sala."
            saved_suggestion = await LetterSuggestionDocument.find_one(
                LetterSuggestionDocument.id == suggestion.id
            )
            assert saved_suggestion is not None
            assert saved_suggestion.status == "accepted"
            state = await DocumentStateDocument.find_one(
                DocumentStateDocument.document_id == document.id
            )
            assert state is not None and state.last_sequence == 1
            assert (
                await CollaborationUpdateDocument.find(
                    CollaborationUpdateDocument.document_id == document.id
                ).count()
                == 1
            )
            assert await client[database_name].command("ping")
        finally:
            await client.drop_database(database_name)
            await client.close()

    asyncio.run(exercise())
