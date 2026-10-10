from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from beanie import init_beanie
from fastapi import HTTPException, Request, status
from pymongo import AsyncMongoClient
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from app.core.config import Settings
from app.modules.auth.documents import (
    InvitationDocument,
    LoginAttemptDocument,
    SchemaMigrationDocument,
    SessionDocument,
    UserDocument,
)
from app.modules.contact.documents import ContactDocument
from app.modules.template.documents import TemplateDocument


SCHEMA_VERSION = 3


def create_mongo_client(settings: Settings) -> AsyncMongoClient:
    return AsyncMongoClient(
        settings.MONGODB_URI.get_secret_value(),
        appname="scesi-letter",
        uuidRepresentation="standard",
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
    async with await client.start_session() as session:
        async with session.start_transaction(
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
            InvitationDocument,
            LoginAttemptDocument,
            SessionDocument,
            SchemaMigrationDocument,
        ],
    )

    latest_migration = await SchemaMigrationDocument.find_all().sort(-SchemaMigrationDocument.version).first_or_none()
    if latest_migration is None:
        latest_migration = SchemaMigrationDocument(
            version=1,
            name="initial_auth_schema",
        )
        await latest_migration.insert()

    if latest_migration is not None and latest_migration.version > SCHEMA_VERSION:
        raise RuntimeError("Database schema is newer than this application version")

    current_version = latest_migration.version if latest_migration is not None else 0
    migrations = {
        2: "persistent_auth_and_login_limits",
        3: "default_template_revisions",
    }
    for version, name in migrations.items():
        if current_version < version:
            await SchemaMigrationDocument(version=version, name=name).insert()

    from app.core.config import get_settings
    from app.modules.template.services import TemplateService

    await TemplateService().seed_default_template(get_settings())
