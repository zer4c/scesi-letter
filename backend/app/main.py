from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.routes import router as core_router
from app.modules.automation.routes import router as automation_router


app = FastAPI(
    title="SCESI Automation API",
    version="0.1.0",
    description="API base for automations without external persistence.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://localhost:5173", "http://localhost:8080"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(core_router)
app.include_router(automation_router)
