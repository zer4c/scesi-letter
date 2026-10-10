from uuid import UUID

from pymongo.asynchronous.client_session import AsyncClientSession

from app.modules.auth.documents import InvitationDocument, SessionDocument, UserDocument


class UserRepository:
    async def get_by_id(
        self, user_id: UUID, session: AsyncClientSession | None = None
    ) -> UserDocument | None:
        return await UserDocument.find_one(UserDocument.id == user_id, session=session)

    async def get_by_email(
        self, normalized_email: str, session: AsyncClientSession | None = None
    ) -> UserDocument | None:
        return await UserDocument.find_one(
            UserDocument.normalized_email == normalized_email,
            session=session,
        )

    async def insert(
        self, user: UserDocument, session: AsyncClientSession | None = None
    ) -> UserDocument:
        return await user.insert(session=session)


class InvitationRepository:
    async def get_by_token_hash(
        self, token_hash: str, session: AsyncClientSession | None = None
    ) -> InvitationDocument | None:
        return await InvitationDocument.find_one(
            InvitationDocument.token_hash == token_hash,
            session=session,
        )

    async def insert(
        self, invitation: InvitationDocument, session: AsyncClientSession | None = None
    ) -> InvitationDocument:
        return await invitation.insert(session=session)


class SessionRepository:
    async def get_by_token_hash(
        self, token_hash: str, session: AsyncClientSession | None = None
    ) -> SessionDocument | None:
        return await SessionDocument.find_one(
            SessionDocument.token_hash == token_hash,
            session=session,
        )

    async def insert(
        self, session_document: SessionDocument, session: AsyncClientSession | None = None
    ) -> SessionDocument:
        return await session_document.insert(session=session)
