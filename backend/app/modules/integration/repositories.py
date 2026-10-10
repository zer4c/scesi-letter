from datetime import UTC, datetime
from uuid import UUID

from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession

from app.modules.integration.documents import DriveArchiveJobDocument


class DriveArchiveJobRepository:
    async def enqueue(
        self,
        document_id: UUID,
        version_id: UUID,
        user_id: UUID,
        session: AsyncClientSession,
    ) -> None:
        job = DriveArchiveJobDocument(
            document_id=document_id,
            version_id=version_id,
            user_id=user_id,
        )
        await DriveArchiveJobDocument.get_pymongo_collection().update_one(
            {"version_id": version_id},
            {"$setOnInsert": job.model_dump(by_alias=True)},
            upsert=True,
            session=session,
        )

    async def request_retry(
        self,
        job: DriveArchiveJobDocument,
        actor_id: UUID,
        topic: str | None,
        confirm_miscellaneous: bool,
    ) -> DriveArchiveJobDocument:
        now = datetime.now(UTC)
        values = {
            "status": "queued",
            "attempt": 0,
            "actor_id": actor_id,
            "error_code": None,
            "next_attempt_at": None,
            "lease_owner": None,
            "lease_until": None,
            "updated_at": now,
        }
        if topic is not None:
            values["topic_category_override"] = topic
            values["confirm_miscellaneous"] = confirm_miscellaneous
        collection = DriveArchiveJobDocument.get_pymongo_collection()
        raw = await collection.find_one_and_update(
            {
                "_id": job.id,
                "status": {
                    "$in": [
                        "failed", "waiting_connection", "needs_classification", "retry_wait"
                    ]
                },
            },
            {"$set": values},
            return_document=ReturnDocument.AFTER,
        )
        if raw is None:
            raw = await collection.find_one({"_id": job.id})
        if raw is None:
            raise RuntimeError("Archive job disappeared during retry")
        return DriveArchiveJobDocument.model_validate(raw)
