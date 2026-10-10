import re
from uuid import UUID

from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.modules.auth.documents import UserDocument
from app.modules.contact.documents import ContactDocument
from app.modules.contact.repositories import ContactRepository
from app.modules.contact.schemas import (
    ContactCreate,
    ContactPage,
    ContactResponse,
    ContactUpdate,
    GoogleContactImportResponse,
)


class ContactService:
    def __init__(self) -> None:
        self._contacts = ContactRepository()

    @staticmethod
    def _email_keys(emails: list[str]) -> list[str] | None:
        return sorted({email.strip().casefold() for email in emails}) or None

    @staticmethod
    def _response(contact: ContactDocument) -> ContactResponse:
        return ContactResponse(
            id=contact.id,
            name=contact.name,
            role_key=contact.role_key,
            role_label=contact.role_label,
            institution=contact.institution,
            career=contact.career,
            emails=contact.emails,
            active=contact.active,
            revision=contact.revision,
            created_by=contact.created_by,
            created_at=contact.created_at,
            updated_at=contact.updated_at,
        )

    async def search(
        self,
        page: int,
        page_size: int,
        query: str | None,
        role_key: str | None,
        institution: str | None,
        career: str | None,
        include_inactive: bool,
    ) -> ContactPage:
        filters: dict[str, object] = {}
        if not include_inactive:
            filters["active"] = True
        if role_key:
            filters["role_key"] = role_key.strip().lower()
        if institution:
            filters["institution"] = institution.strip()
        if career:
            filters["career"] = career.strip()
        if query:
            escaped = re.escape(query.strip())
            filters["$or"] = [
                {"name": {"$regex": escaped, "$options": "i"}},
                {"role_label": {"$regex": escaped, "$options": "i"}},
                {"institution": {"$regex": escaped, "$options": "i"}},
                {"career": {"$regex": escaped, "$options": "i"}},
                {"emails": {"$regex": escaped, "$options": "i"}},
            ]
        contacts, total = await self._contacts.list_page(filters, page, page_size)
        return ContactPage(
            items=[self._response(contact) for contact in contacts],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def get(self, contact_id: UUID) -> ContactResponse:
        contact = await self._contacts.get_by_id(contact_id)
        if contact is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        return self._response(contact)

    async def create(self, payload: ContactCreate, actor: UserDocument) -> ContactResponse:
        now_values = payload.model_dump()
        emails = [str(email) for email in now_values.pop("emails")]
        contact = ContactDocument(
            **now_values,
            emails=emails,
            normalized_emails=self._email_keys(emails),
            created_by=actor.id,
        )
        try:
            await self._contacts.insert(contact)
        except DuplicateKeyError as error:
            raise HTTPException(status_code=409, detail="CONFLICT") from error
        return self._response(contact)

    async def import_google_contacts(
        self, payloads: list[ContactCreate], actor: UserDocument
    ) -> GoogleContactImportResponse:
        imported: list[ContactResponse] = []
        skipped = 0
        collection = ContactDocument.get_pymongo_collection()
        for payload in payloads:
            values = payload.model_dump()
            emails = [str(email).casefold() for email in values.pop("emails")]
            keys = self._email_keys(emails)
            if keys and await collection.find_one({"normalized_emails": {"$in": keys}}):
                skipped += 1
                continue
            contact = ContactDocument(
                **values, emails=emails, normalized_emails=keys, created_by=actor.id
            )
            try:
                await self._contacts.insert(contact)
            except DuplicateKeyError:
                skipped += 1
                continue
            imported.append(self._response(contact))
        return GoogleContactImportResponse(imported=imported, skipped_duplicates=skipped)

    async def update(
        self,
        contact_id: UUID,
        payload: ContactUpdate,
    ) -> ContactResponse:
        current = await self._contacts.get_by_id(contact_id)
        if current is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        if current.revision != payload.expected_revision:
            raise HTTPException(status_code=409, detail="CONFLICT")
        values = payload.model_dump(
            exclude={"expected_revision"}, exclude_unset=True
        )
        if "emails" in values:
            values["emails"] = [str(email) for email in values["emails"]]
            values["normalized_emails"] = self._email_keys(values["emails"])
        try:
            result = await self._contacts.update(
                contact_id, payload.expected_revision, values
            )
        except DuplicateKeyError as error:
            raise HTTPException(status_code=409, detail="CONFLICT") from error
        if result.modified_count != 1:
            raise HTTPException(status_code=409, detail="CONFLICT")
        updated = await self._contacts.get_by_id(contact_id)
        if updated is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        return self._response(updated)
