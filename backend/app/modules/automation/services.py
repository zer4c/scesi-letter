from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException

from app.modules.automation.schemas import Automation, AutomationCreate, RunResult


class AutomationService:
    def __init__(self) -> None:
        self._automations: dict[UUID, Automation] = {}

    def list(self) -> list[Automation]:
        return list(self._automations.values())

    def create(self, payload: AutomationCreate) -> Automation:
        automation = Automation(
            id=uuid4(),
            created_at=datetime.now(timezone.utc),
            **payload.model_dump(),
        )
        self._automations[automation.id] = automation
        return automation

    def run(self, automation_id: UUID) -> RunResult:
        automation = self._automations.get(automation_id)
        if automation is None:
            raise HTTPException(status_code=404, detail="Automation not found")
        return RunResult(
            automation_id=automation.id,
            status="completed",
            executed_at=datetime.now(timezone.utc),
            message=f"Action '{automation.action}' completed successfully",
        )


automation_service = AutomationService()
