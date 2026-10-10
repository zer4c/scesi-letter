from uuid import UUID

from fastapi import APIRouter, status

from app.core.config import API_PREFIX
from app.modules.automation.schemas import Automation, AutomationCreate, RunResult
from app.modules.automation.services import automation_service


router = APIRouter(prefix=f"{API_PREFIX}/automations", tags=["automations"])


@router.get("", response_model=list[Automation])
def list_automations() -> list[Automation]:
    return automation_service.list()


@router.post("", response_model=Automation, status_code=status.HTTP_201_CREATED)
def create_automation(payload: AutomationCreate) -> Automation:
    return automation_service.create(payload)


@router.post("/{automation_id}/run", response_model=RunResult)
def run_automation(automation_id: UUID) -> RunResult:
    return automation_service.run(automation_id)
