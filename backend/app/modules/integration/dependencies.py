from fastapi import Depends

from app.core.config import Settings, get_settings
from app.modules.integration.services import GoogleConnectionService


def google_connection_service(
    settings: Settings = Depends(get_settings),
) -> GoogleConnectionService:
    return GoogleConnectionService(settings)
