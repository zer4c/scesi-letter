from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.database import create_mongo_client, initialize_persistence
from app.modules.collaboration.services import CollaborationService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    client = create_mongo_client(settings)
    app.state.mongo_client = client
    app.state.database = client[settings.MONGODB_DATABASE]
    app.state.collaboration_service = CollaborationService(client)
    try:
        await initialize_persistence(app.state.database)
        yield
    finally:
        await client.close()
