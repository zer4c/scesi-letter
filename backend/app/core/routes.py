from fastapi import APIRouter, Depends
from pymongo import AsyncMongoClient

from app.core.config import API_PREFIX, get_settings
from app.core.database import check_database, get_mongo_client


router = APIRouter(prefix=API_PREFIX, tags=["system"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "scesi-automation-api"}


@router.get("/ready")
async def readiness(
    client: AsyncMongoClient = Depends(get_mongo_client),
) -> dict[str, str]:
    await check_database(client, get_settings().MONGODB_REPLICA_SET)
    return {"status": "ready", "database": "ready"}
