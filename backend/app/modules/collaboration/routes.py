import asyncio
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.modules.auth.services import AuthService, CSRF_COOKIE
from app.modules.collaboration.services import (
    MAX_FRAME_BYTES,
    CollaborationService,
    InvalidCollaborationMessage,
)
from app.modules.document.documents import LetterDocument
from app.modules.document.services import DocumentService


router = APIRouter(tags=["collaboration"])
REAUTHENTICATE_SECONDS = 15


@router.websocket("/ws/documents/{document_id}")
async def collaborate(websocket: WebSocket, document_id: UUID) -> None:
    settings = get_settings()
    offered_protocols = websocket.scope.get("subprotocols", [])
    origin = websocket.headers.get("origin")
    csrf_cookie = websocket.cookies.get(CSRF_COOKIE)
    if (
        origin not in settings.cors_origins
        or "yjs" not in offered_protocols
        or not csrf_cookie
    ):
        await websocket.close(code=4403)
        return

    auth = AuthService(settings)
    try:
        actor = await auth.authenticate_request(websocket)
        auth.csrf_token(websocket)
    except Exception:
        await websocket.close(code=4401)
        return

    document = await LetterDocument.find_one(LetterDocument.id == document_id)
    if document is None:
        await websocket.close(code=4404)
        return
    try:
        DocumentService._authorize(document, actor)
    except Exception:
        await websocket.close(code=4403)
        return

    service: CollaborationService = websocket.app.state.collaboration_service
    try:
        room = await service.open_room(document)
    except InvalidCollaborationMessage:
        await websocket.close(code=4429)
        return
    except Exception:
        await websocket.close(code=1011)
        return

    await websocket.accept(subprotocol="yjs")
    try:
        try:
            await service.add_client(room, websocket)
        except InvalidCollaborationMessage:
            await websocket.close(code=4429)
            return
        while True:
            try:
                message = await asyncio.wait_for(
                    websocket.receive_bytes(), timeout=REAUTHENTICATE_SECONDS
                )
            except TimeoutError:
                message = None

            try:
                actor = await auth.authenticate_request(websocket)
                auth.csrf_token(websocket)
                current_document = await LetterDocument.find_one(
                    LetterDocument.id == document_id
                )
                if current_document is None:
                    await websocket.close(code=4404)
                    return
                DocumentService._authorize(current_document, actor)
                room.document = current_document
            except Exception:
                await websocket.close(code=4403)
                return

            if message is None:
                continue
            if len(message) > MAX_FRAME_BYTES:
                await websocket.close(code=1009)
                return
            try:
                await service.process_message(room, websocket, message, actor)
            except InvalidCollaborationMessage:
                await websocket.close(code=1008)
                return
    except WebSocketDisconnect:
        pass
    finally:
        await service.remove_client(document_id, room, websocket)
