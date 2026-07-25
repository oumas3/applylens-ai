from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict

router = APIRouter(
    prefix="/api/v1/tasks",
    tags=["tasks"],
)


class TaskItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: int
    title: str
    status: str


DEFAULT_TASKS = [
    TaskItem(id=1, title="Gather supporting documents", status="pending"),
    TaskItem(id=2, title="Check application deadlines", status="pending"),
    TaskItem(id=3, title="Prepare funding statement", status="pending"),
]


@router.get("", response_model=list[TaskItem], status_code=status.HTTP_200_OK)
def list_tasks() -> list[TaskItem]:
    return DEFAULT_TASKS
