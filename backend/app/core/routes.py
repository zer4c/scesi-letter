from fastapi import APIRouter

from app.core.config import API_PREFIX


router = APIRouter(prefix=API_PREFIX, tags=["system"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "scesi-automation-api"}
