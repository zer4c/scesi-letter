from pymongo.asynchronous.client_session import AsyncClientSession

from app.modules.template.documents import TemplateDocument


class TemplateRepository:
    async def get_revision(self, revision: int) -> TemplateDocument | None:
        return await TemplateDocument.find_one(
            TemplateDocument.template_id == "default",
            TemplateDocument.revision == revision,
        )

    async def get_active(
        self, session: AsyncClientSession | None = None
    ) -> TemplateDocument | None:
        return await TemplateDocument.find_one(
            TemplateDocument.template_id == "default",
            TemplateDocument.active == True,
            session=session,
        )

    async def insert(
        self,
        template: TemplateDocument,
        session: AsyncClientSession | None = None,
    ) -> TemplateDocument:
        return await template.insert(session=session)

    async def save(
        self,
        template: TemplateDocument,
        session: AsyncClientSession,
    ) -> TemplateDocument:
        return await template.save(session=session)
