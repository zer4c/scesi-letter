from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.core.config import Settings, get_settings
from app.modules.auth.documents import UserDocument
from app.modules.auth.routes import require_current_user
from app.modules.document.markdown_source import InvalidMarkdownSource
from app.modules.document.pdf_renderer import InvalidMarkdown, RenderLimitExceeded
from app.modules.document.schemas import RenderRequest
from app.modules.document.services import DocumentRenderService
from app.modules.template.services import TemplateService


router = APIRouter(prefix="/documents", tags=["document rendering"])


@router.post("/preview", response_class=Response)
async def render_preview(
    payload: RenderRequest,
    _actor: UserDocument = Depends(require_current_user),
    settings: Settings = Depends(get_settings),
) -> Response:
    try:
        template = await TemplateService().get_current()
        content, content_hash = DocumentRenderService(settings).preview(
            payload.markdown,
            template.settings,
        )
    except (InvalidMarkdownSource, InvalidMarkdown, RecursionError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="VALIDATION_ERROR",
        ) from error
    except RenderLimitExceeded as error:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="VALIDATION_ERROR",
        ) from error
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": 'inline; filename="preview.pdf"',
            "X-Content-SHA256": content_hash,
        },
    )
