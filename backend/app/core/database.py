from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from beanie import init_beanie
from fastapi import HTTPException, Request, status
from pymongo import AsyncMongoClient
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError, PyMongoError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from app.core.config import Settings
from app.modules.auth.documents import (
    InvitationDocument,
    LoginAttemptDocument,
    SchemaMigrationDocument,
    SessionDocument,
    SignatureEnvelopeDocument,
    UserDocument,
)
from app.modules.contact.documents import ContactDocument
from app.modules.collaboration.documents import (
    CollaborationUpdateDocument,
    DocumentStateDocument,
)
from app.modules.document.documents import (
    DocumentVersionDocument,
    ExportJobDocument,
    LetterCounterDocument,
    LetterDocument,
)
from app.modules.event.documents import EventDocument
from app.modules.integration.documents import (
    IntegrationConnectionDocument,
    OAuthStateDocument,
)
from app.modules.signature.documents import SigningAuthorizationDocument
from app.modules.template.documents import TemplateDocument


SCHEMA_VERSION = 10


def create_mongo_client(settings: Settings) -> AsyncMongoClient:
    return AsyncMongoClient(
        settings.MONGODB_URI.get_secret_value(),
        appname="scesi-letter",
        uuidRepresentation="standard",
        tz_aware=True,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        maxPoolSize=30,
    )


async def check_database(client: AsyncMongoClient, replica_set: str) -> None:
    try:
        await client.admin.command("ping")
        hello = await client.admin.command("hello")
    except PyMongoError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from error

    if hello.get("setName") != replica_set:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database replica set is not ready",
        )


def get_mongo_client(request: Request) -> AsyncMongoClient:
    return request.app.state.mongo_client


@asynccontextmanager
async def transaction(client: AsyncMongoClient) -> AsyncIterator[AsyncClientSession]:
    async with client.start_session() as session:
        async with await session.start_transaction(
            read_concern=ReadConcern("snapshot"),
            write_concern=WriteConcern("majority"),
        ):
            yield session


async def initialize_persistence(database: AsyncDatabase) -> None:
    await init_beanie(
        database=database,
        document_models=[
            UserDocument,
            ContactDocument,
            TemplateDocument,
            LetterDocument,
            DocumentVersionDocument,
            LetterCounterDocument,
            ExportJobDocument,
            DocumentStateDocument,
            CollaborationUpdateDocument,
            InvitationDocument,
            LoginAttemptDocument,
            SessionDocument,
            SignatureEnvelopeDocument,
            SigningAuthorizationDocument,
            SchemaMigrationDocument,
            EventDocument,
            IntegrationConnectionDocument,
            OAuthStateDocument,
        ],
    )

    latest_migration = await SchemaMigrationDocument.find_all().sort(-SchemaMigrationDocument.version).first_or_none()
    if latest_migration is not None and latest_migration.version > SCHEMA_VERSION:
        raise RuntimeError("Database schema is newer than this application version")

    migrations = {
        1: "initial_auth_schema",
        2: "persistent_auth_and_login_limits",
        3: "default_template_revisions",
        4: "document_versioned_source",
        5: "durable_collaboration_state",
        6: "academic_events",
        7: "owner_signature_envelopes",
        8: "user_credential_revisions",
        9: "one_use_signing_authorizations",
        10: "encrypted_google_connections",
    }
    migration_collection = SchemaMigrationDocument.get_pymongo_collection()
    for version, name in migrations.items():
        try:
            await migration_collection.update_one(
                {"version": version},
                {
                    "$setOnInsert": {
                        "name": name,
                        "applied_at": datetime.now(UTC),
                    }
                },
                upsert=True,
            )
        except DuplicateKeyError:
            pass

    await UserDocument.get_pymongo_collection().update_many(
        {"credential_revision": {"$exists": False}},
        {"$set": {"credential_revision": 1}},
    )

    from app.core.config import get_settings
    from app.modules.template.services import TemplateService

    await TemplateService().seed_default_template(get_settings())
