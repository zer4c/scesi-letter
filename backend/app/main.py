from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.core.errors import http_exception_handler, validation_exception_handler
from app.core.lifespan import lifespan
from app.core.routes import router as core_router
from app.modules.automation.routes import router as automation_router
from app.modules.auth.routes import membership_router, router as auth_router
from app.modules.contact.routes import router as contact_router
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
app.include_router(automation_router)
