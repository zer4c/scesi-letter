from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.database import create_mongo_client


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    client = create_mongo_client(settings)
    app.state.mongo_client = client
    app.state.database = client[settings.MONGODB_DATABASE]
    try:
        yield
    finally:
        await client.close()
