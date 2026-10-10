from datetime import UTC, datetime

from fastapi import HTTPException
from pymongo import AsyncMongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.core.config import Settings
from app.core.database import transaction
from app.modules.template.documents import TemplateDocument
from app.modules.template.repositories import TemplateRepository
from app.modules.template.schemas import TemplateResponse, TemplateSettings


class TemplateService:
    def __init__(self) -> None:
        self._templates = TemplateRepository()

    @staticmethod
    def initial_settings(settings: Settings) -> TemplateSettings:
        return TemplateSettings(
            university_name="Universidad Mayor de San Simón",
            faculty_name="Facultad de Ciencias y Tecnología",
            organization_name="Sociedad Científica de Estudiantes de Sistemas e Informática",
            footer_phones=settings.TEMPLATE_FOOTER_PHONES,
            footer_url=settings.TEMPLATE_FOOTER_URL,
            qr_destination=settings.TEMPLATE_QR_URL,
            footer_email=settings.TEMPLATE_FOOTER_EMAIL,
            footer_address=settings.TEMPLATE_FOOTER_ADDRESS,
        )

    @staticmethod
    def response(template: TemplateDocument) -> TemplateResponse:
        return TemplateResponse(
            template_id=template.template_id,
            revision=template.revision,
            settings=template.settings,
            created_at=template.created_at,
        )

    async def seed_default_template(self, settings: Settings) -> None:
        if await self._templates.get_active() is not None:
            return
        try:
            await self._templates.insert(
                TemplateDocument(
                    revision=1,
                    settings=self.initial_settings(settings),
                )
            )
        except DuplicateKeyError:
            if await self._templates.get_active() is None:
                raise

    async def get_current(self) -> TemplateResponse:
        template = await self._templates.get_active()
        if template is None:
            raise HTTPException(status_code=503, detail="INTERNAL_ERROR")
        return self.response(template)

    async def update(
        self,
        payload_revision: int,
        settings: TemplateSettings,
        actor_id: str,
        client: AsyncMongoClient,
    ) -> TemplateResponse:
        now = datetime.now(UTC)
        try:
            async with transaction(client) as session:
                current = await self._templates.get_active(session=session)
                if current is None:
                    raise HTTPException(status_code=503, detail="INTERNAL_ERROR")
                if current.revision != payload_revision:
                    raise HTTPException(status_code=409, detail="CONFLICT")
                current.active = False
                await self._templates.save(current, session)
                updated = TemplateDocument(
                    template_id=current.template_id,
                    revision=current.revision + 1,
                    active=True,
                    settings=settings,
                    created_by=actor_id,
                    created_at=now,
                )
                await self._templates.insert(updated, session)
                return self.response(updated)
        except DuplicateKeyError as error:
            raise HTTPException(status_code=409, detail="CONFLICT") from error
        except PyMongoError as error:
            if error.code == 112 or error.has_error_label("TransientTransactionError"):
                raise HTTPException(status_code=409, detail="CONFLICT") from error
            raise
