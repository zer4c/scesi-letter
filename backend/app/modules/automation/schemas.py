from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AutomationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    action: Literal["notify", "generate_report", "webhook"] = "notify"


class Automation(AutomationCreate):
    id: UUID
    created_at: datetime
    enabled: bool = True


class RunResult(BaseModel):
    automation_id: UUID
    status: Literal["completed"]
    executed_at: datetime
    message: str
