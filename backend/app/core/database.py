from fastapi import HTTPException, Request, status
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError

from app.core.config import Settings


def create_mongo_client(settings: Settings) -> AsyncMongoClient:
    return AsyncMongoClient(
        settings.MONGODB_URI.get_secret_value(),
        appname="scesi-letter",
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
