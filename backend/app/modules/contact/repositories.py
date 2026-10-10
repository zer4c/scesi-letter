from datetime import UTC, datetime
from uuid import UUID

from pymongo import ASCENDING
from pymongo.results import UpdateResult

from app.modules.contact.documents import ContactDocument


class ContactRepository:
    async def list_page(
        self,
        filters: dict[str, object],
        page: int,
        page_size: int,
    ) -> tuple[list[ContactDocument], int]:
        collection = ContactDocument.get_pymongo_collection()
        total = await collection.count_documents(filters)
        cursor = (
            collection.find(filters)
            .sort([("name", ASCENDING), ("_id", ASCENDING)])
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        return [ContactDocument.model_validate(raw) async for raw in cursor], total

    async def insert(self, contact: ContactDocument) -> ContactDocument:
        return await contact.insert()

    async def get_by_id(self, contact_id: UUID) -> ContactDocument | None:
        return await ContactDocument.find_one(ContactDocument.id == contact_id)

    async def update(
        self,
        contact_id: UUID,
        expected_revision: int,
        values: dict[str, object],
    ) -> UpdateResult:
        values["updated_at"] = datetime.now(UTC)
        return await ContactDocument.get_pymongo_collection().update_one(
            {"_id": contact_id, "revision": expected_revision},
            {"$set": values, "$inc": {"revision": 1}},
        )
