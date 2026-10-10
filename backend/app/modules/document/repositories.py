from uuid import UUID
from uuid import uuid4

from pymongo import ASCENDING
from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession

from app.modules.document.documents import (
    DocumentVersionDocument,
    ExportJobDocument,
    LetterCounterDocument,
    LetterDocument,
)


class LetterRepository:
    async def insert(
        self, document: LetterDocument, session: AsyncClientSession | None = None
    ) -> LetterDocument:
        return await document.insert(session=session)

    async def get_by_id(
        self, document_id: UUID, session: AsyncClientSession | None = None
    ) -> LetterDocument | None:
        return await LetterDocument.find_one(
            LetterDocument.id == document_id,
            session=session,
        )

    async def save(
        self, document: LetterDocument, session: AsyncClientSession
    ) -> LetterDocument:
        return await document.save(session=session)

    async def list_page(
        self,
        actor_id: UUID,
        is_admin: bool,
        page: int,
        page_size: int,
    ) -> tuple[list[LetterDocument], int]:
        collection = LetterDocument.get_pymongo_collection()
        query: dict[str, object] = (
            {} if is_admin else {"$or": [{"owner_id": actor_id}, {"participant_ids": actor_id}]}
        )
        total = await collection.count_documents(query)
        cursor = (
            collection.find(query)
            .sort([("updated_at", -1), ("_id", ASCENDING)])
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        items = [LetterDocument.model_validate(raw) async for raw in cursor]
        return items, total


class VersionRepository:
    async def insert(
        self,
        version: DocumentVersionDocument,
        session: AsyncClientSession,
    ) -> DocumentVersionDocument:
        return await version.insert(session=session)

    async def get_by_id(
        self,
        document_id: UUID,
        version_id: UUID,
        session: AsyncClientSession | None = None,
    ) -> DocumentVersionDocument | None:
        return await DocumentVersionDocument.find_one(
            DocumentVersionDocument.document_id == document_id,
            DocumentVersionDocument.id == version_id,
            session=session,
        )

    async def get_current(
        self,
        document_id: UUID,
        session: AsyncClientSession | None = None,
    ) -> DocumentVersionDocument | None:
        return await DocumentVersionDocument.find_one(
            DocumentVersionDocument.document_id == document_id,
            sort=[("version_number", -1)],
            session=session,
        )

    async def list_for_document(
        self, document_id: UUID
    ) -> list[DocumentVersionDocument]:
        return await DocumentVersionDocument.find(
            DocumentVersionDocument.document_id == document_id
        ).sort(-DocumentVersionDocument.version_number).to_list()


class LetterCounterRepository:
    async def allocate(
        self,
        organization: str,
        document_type: str,
        year: int,
        session: AsyncClientSession,
    ) -> int:
        counter = await LetterCounterDocument.get_pymongo_collection().find_one_and_update(
            {
                "organization": organization,
                "document_type": document_type,
                "year": year,
            },
            {
                "$inc": {"value": 1},
                "$setOnInsert": {"_id": uuid4()},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
            session=session,
        )
        return int(counter["value"])


class ExportJobRepository:
    async def insert(
        self,
        job: ExportJobDocument,
        session: AsyncClientSession,
    ) -> ExportJobDocument:
        return await job.insert(session=session)
