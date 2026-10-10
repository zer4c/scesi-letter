import re
import unicodedata
from uuid import UUID

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from app.modules.auth.documents import UserDocument
from app.modules.event.documents import EventDocument
from app.modules.event.schemas import EventCreate, EventPage, EventResponse


class EventService:
    @staticmethod
    def _slug(name: str) -> str:
        normalized = unicodedata.normalize("NFKD", name.strip().casefold())
        ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
        slug = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")
        if not slug:
            raise HTTPException(status_code=422, detail="VALIDATION_ERROR")
        return slug[:140].rstrip("-")

    async def list(self, year: int | None, page: int, page_size: int) -> EventPage:
        query = (
            EventDocument.find_all()
            if year is None
            else EventDocument.find(EventDocument.year == year)
        )
        total = await query.count()
        events = await (
            query.sort([("year", -1), ("name", 1)])
            .skip((page - 1) * page_size)
            .limit(page_size)
            .to_list()
        )
        return EventPage(
            items=[EventResponse.model_validate(event.model_dump()) for event in events],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def create(self, payload: EventCreate, actor: UserDocument) -> EventResponse:
        event = EventDocument(
            slug=self._slug(payload.name),
            name=payload.name.strip(),
            year=payload.year,
            created_by=actor.id,
        )
        try:
            await event.insert()
        except DuplicateKeyError as error:
            raise HTTPException(status_code=409, detail="CONFLICT") from error
        return EventResponse.model_validate(event.model_dump())

    async def get(self, event_id: UUID) -> EventResponse:
        event = await EventDocument.find_one(EventDocument.id == event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        return EventResponse.model_validate(event.model_dump())
