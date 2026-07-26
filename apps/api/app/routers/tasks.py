from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(
    prefix="/api/v1/tasks",
    tags=["tasks"],
)


class TaskItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: int
    title: str
    status: Literal["pending", "in_progress", "completed"]


class TaskStatusUpdate(BaseModel):
    status: Literal["pending", "in_progress", "completed"]


class TaskGenerationRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    missing_requirements: list[str] = Field(default_factory=list)
    deadline: str | None = None
    funding: str | None = None


DEFAULT_TASKS = [
    TaskItem(id=1, title="Gather supporting documents", status="pending"),
    TaskItem(id=2, title="Check application deadlines", status="pending"),
    TaskItem(id=3, title="Prepare funding statement", status="pending"),
]
tasks = DEFAULT_TASKS.copy()


@router.get("", response_model=list[TaskItem], status_code=status.HTTP_200_OK)
def list_tasks() -> list[TaskItem]:
    return tasks


@router.post(
    "/generate",
    response_model=list[TaskItem],
    status_code=status.HTTP_200_OK,
)
def generate_tasks(request: TaskGenerationRequest) -> list[TaskItem]:
    global tasks

    task_titles = [
        f"Provide evidence for: {requirement}"
        for requirement in request.missing_requirements
        if requirement.strip()
    ]

    if request.deadline and request.deadline.strip():
        task_titles.append(f"Confirm application deadline: {request.deadline}")

    if request.funding and request.funding.strip():
        task_titles.append("Review funding requirements and available support")

    tasks = [
        TaskItem(id=index, title=title, status="pending")
        for index, title in enumerate(task_titles, start=1)
    ]
    return tasks


@router.patch(
    "/{task_id}",
    response_model=TaskItem,
    status_code=status.HTTP_200_OK,
)
def update_task_status(task_id: int, update: TaskStatusUpdate) -> TaskItem:
    for index, task in enumerate(tasks):
        if task.id == task_id:
            updated_task = task.model_copy(update={"status": update.status})
            tasks[index] = updated_task
            return updated_task

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Task not found.",
    )
