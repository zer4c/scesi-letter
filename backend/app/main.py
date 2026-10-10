from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.core.errors import http_exception_handler, validation_exception_handler
from app.core.lifespan import lifespan
from app.core.routes import router as core_router
from app.modules.auth.routes import membership_router
from app.modules.auth.routes import router as auth_router
from app.modules.automation.routes import router as automation_router
from app.modules.collaboration.routes import router as collaboration_router
from app.modules.contact.routes import router as contact_router
from app.modules.document.routes import job_router
from app.modules.document.routes import router as document_router
from app.modules.event.routes import router as event_router
from app.modules.integration.routes import archive_router
from app.modules.integration.routes import router as integration_router
from app.modules.signature.routes import document_signing_router
from app.modules.signature.routes import password_router as signature_password_router
from app.modules.signature.routes import router as signature_router
from app.modules.template.routes import router as template_router

settings = get_settings()
app = FastAPI(
    title="SCESI Automation API",
    version="0.1.0",
    description="Academic letter automation API.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key"],
)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    request.state.request_id = uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


app.include_router(core_router)
app.include_router(auth_router, prefix=settings.API_PREFIX)
app.include_router(membership_router, prefix=settings.API_PREFIX)
app.include_router(contact_router, prefix=settings.API_PREFIX)
app.include_router(template_router, prefix=settings.API_PREFIX)
app.include_router(document_router, prefix=settings.API_PREFIX)
app.include_router(event_router, prefix=settings.API_PREFIX)
app.include_router(integration_router, prefix=settings.API_PREFIX)
app.include_router(archive_router, prefix=settings.API_PREFIX)
app.include_router(signature_router, prefix=settings.API_PREFIX)
app.include_router(signature_password_router, prefix=settings.API_PREFIX)
app.include_router(document_signing_router, prefix=settings.API_PREFIX)
app.include_router(job_router, prefix=settings.API_PREFIX)
app.include_router(collaboration_router)
app.include_router(automation_router, prefix=settings.API_PREFIX)
