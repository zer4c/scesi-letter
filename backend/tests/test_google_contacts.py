import asyncio
from types import SimpleNamespace
from uuid import uuid4

import httpx
from fastapi import HTTPException
import pytest
from pymongo.errors import DuplicateKeyError

from app.core.config import Settings
from app.modules.contact.documents import ContactDocument
from app.modules.contact.schemas import ContactCreate
from app.modules.contact.services import ContactService
from app.modules.integration.services import (
    GOOGLE_OTHER_CONTACTS_ENDPOINT,
    GoogleConnectionService,
    PROVIDER_SCOPES,
)


def test_other_contacts_preview_paginates_and_requests_only_public_fields():
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "otherContacts": [
                    {
                        "names": [{"displayName": "Academic Contact"}],
                        "emailAddresses": [{"value": "person@example.com"}],
                        "phoneNumbers": [{"value": "+1 555 0100"}],
                        "biographies": [{"value": "Private note"}],
                    }
                ],
                "nextPageToken": "next-page",
            },
        )

    service = GoogleConnectionService(Settings(), httpx.MockTransport(respond))
    connection = SimpleNamespace(
        kind="contacts", mode="personal", scopes=[PROVIDER_SCOPES["contacts"]]
    )

    async def get_connection(connection_id, actor):
        return connection

    async def get_access_token(authorized_connection, actor):
        assert authorized_connection is connection
        return "synthetic-access-token"

    service._get_authorized_connection = get_connection
    service.get_access_token = get_access_token

    result = asyncio.run(
        service.list_other_contacts(uuid4(), SimpleNamespace(), "next-page")
    )

    assert result == {
        "items": [{"name": "Academic Contact", "email": "person@example.com"}],
        "next_page_token": "next-page",
    }
    assert requests[0].url.path == GOOGLE_OTHER_CONTACTS_ENDPOINT.removeprefix(
        "https://people.googleapis.com"
    )
    assert dict(requests[0].url.params) == {
        "readMask": "names,emailAddresses",
        "pageSize": "100",
        "pageToken": "next-page",
    }
    assert requests[0].headers["Authorization"] == "Bearer synthetic-access-token"


def test_other_contacts_preview_reports_revoked_permission():
    service = GoogleConnectionService(
        Settings(),
        httpx.MockTransport(lambda request: httpx.Response(403, json={"error": "access_denied"})),
    )
    connection = SimpleNamespace(
        kind="contacts", mode="personal", scopes=[PROVIDER_SCOPES["contacts"]]
    )

    async def get_connection(connection_id, actor):
        return connection

    async def get_access_token(authorized_connection, actor):
        return "synthetic-access-token"

    service._get_authorized_connection = get_connection
    service.get_access_token = get_access_token

    with pytest.raises(HTTPException) as error:
        asyncio.run(service.list_other_contacts(uuid4(), SimpleNamespace(), None))

    assert error.value.status_code == 403
    assert error.value.detail == "GOOGLE_SCOPE_MISMATCH"


class FakeContactCollection:
    def __init__(self, existing_emails=()):
        self.existing_emails = set(existing_emails)

    async def find_one(self, query):
        requested = set(query["normalized_emails"]["$in"])
        if requested & self.existing_emails:
            return {"normalized_emails": list(requested & self.existing_emails)}
        return None


class FakeContactRepository:
    def __init__(self, race=False):
        self.inserted = []
        self.race = race

    async def insert(self, contact):
        if self.race:
            raise DuplicateKeyError("duplicate email")
        self.inserted.append(contact)
        return contact


def contact_payload(email, name):
    return ContactCreate(
        name=name,
        role_key="career_director",
        role_label="Career director",
        institution="UMSS",
        emails=[email],
    )


def test_confirmed_import_skips_existing_contacts_without_overwriting(monkeypatch):
    collection = FakeContactCollection({"existing@example.com"})
    monkeypatch.setattr(ContactDocument, "get_pymongo_collection", lambda *args: collection)
    service = ContactService()
    repository = FakeContactRepository()
    service._contacts = repository
    actor = SimpleNamespace(id=uuid4())

    result = asyncio.run(
        service.import_google_contacts(
            [
                contact_payload("existing@example.com", "Existing contact"),
                contact_payload("new@example.com", "New contact"),
            ],
            actor,
        )
    )

    assert result.skipped_duplicates == 1
    assert [item.name for item in result.imported] == ["New contact"]
    assert [item.name for item in repository.inserted] == ["New contact"]
    assert repository.inserted[0].created_by == actor.id


def test_confirmed_import_skips_duplicate_key_race(monkeypatch):
    collection = FakeContactCollection()
    monkeypatch.setattr(ContactDocument, "get_pymongo_collection", lambda *args: collection)
    service = ContactService()
    service._contacts = FakeContactRepository(race=True)

    result = asyncio.run(
        service.import_google_contacts(
            [contact_payload("raced@example.com", "Raced contact")],
            SimpleNamespace(id=uuid4()),
        )
    )

    assert result.imported == []
    assert result.skipped_duplicates == 1
