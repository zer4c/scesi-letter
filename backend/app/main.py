from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.lifespan import lifespan
from app.core.routes import router as core_router
from app.modules.automation.routes import router as automation_router


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
app.include_router(core_router)
app.include_router(automation_router)
