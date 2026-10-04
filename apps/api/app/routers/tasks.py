import json
import logging
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from app.routers.auth import get_current_user
from app.concurrency import guarded
from app.config import get_settings
from app.services.application_store import PostgresApplicationStore
from app.quotas import enforce_account_quota

router = APIRouter(
    prefix="/api/v1/tasks",
    tags=["tasks"],
    dependencies=[Depends(get_current_user)],
)
logger = logging.getLogger(__name__)

TaskRequirement = Annotated[str, StringConstraints(max_length=2_000)]

TASKS_FILE = Path(__file__).resolve().parents[2] / "storage" / "tasks.json"
settings = get_settings()
application_store = (
    PostgresApplicationStore(settings.database_url)
    if settings.database_url
    else None
)


class TaskItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: int
    user_id: str | None = None
    opportunity_id: str | None = Field(default=None, max_length=64)
    title: str = Field(..., min_length=1, max_length=2_100)
    status: Literal["pending", "in_progress", "completed"]


class TaskStatusUpdate(BaseModel):
    status: Literal["pending", "in_progress", "completed"]


class TaskGenerationRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    opportunity_id: str | None = Field(default=None, max_length=64)
    missing_requirements: list[TaskRequirement] = Field(
        default_factory=list,
        max_length=100,
    )
    deadline: str | None = Field(default=None, max_length=500)
    funding: str | None = Field(default=None, max_length=2_000)


DEFAULT_TASKS = [
    TaskItem(id=1, title="Gather supporting documents", status="pending"),
    TaskItem(id=2, title="Check application deadlines", status="pending"),
    TaskItem(id=3, title="Prepare funding statement", status="pending"),
]
def _load_tasks() -> list[TaskItem]:
    if application_store is not None:
        try:
            application_store.load_tasks()
            return []
        except Exception:
            logger.exception("Unable to load tasks from PostgreSQL")
            raise RuntimeError("PostgreSQL tasks could not be loaded.")

    if not TASKS_FILE.exists():
        return DEFAULT_TASKS.copy()

    try:
        payload = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
        return [TaskItem.model_validate(item) for item in payload]
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return DEFAULT_TASKS.copy()


def _persist_tasks(user_id: str | None = None) -> None:
    if application_store is not None:
        application_store.replace_tasks(
            (
                task.model_dump(mode="python")
                for task in tasks
                if user_id is None or task.user_id == user_id
            ),
            user_id=user_id,
        )
        return

    TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TASKS_FILE.write_text(
        json.dumps([task.model_dump(mode="json") for task in tasks], indent=2),
        encoding="utf-8",
    )


tasks = _load_tasks()


def tasks_for_user(user_id: str) -> list[TaskItem]:
    if application_store is not None:
        return [
            TaskItem.model_validate(item)
            for item in application_store.load_tasks(user_id)
        ]
    return [task for task in tasks if task.user_id == user_id]


@router.get("", response_model=list[TaskItem], status_code=status.HTTP_200_OK)
def list_tasks(user: dict[str, str | bool] = Depends(get_current_user)) -> list[TaskItem]:
    return tasks_for_user(str(user["id"]))


@router.post(
    "/generate",
    response_model=list[TaskItem],
    status_code=status.HTTP_200_OK,
)
def generate_tasks(
    request: TaskGenerationRequest,
    user: dict[str, str | bool] = Depends(get_current_user),
) -> list[TaskItem]:
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

    generated_tasks: list[TaskItem] = []

    if application_store is not None:
        generated_records = application_store.replace_task_scope(
            str(user["id"]),
            request.opportunity_id,
            task_titles,
            limit=settings.free_beta_task_limit,
        )
        if generated_records is None:
            enforce_account_quota("task", settings.free_beta_task_limit + 1)
        generated_tasks = [
            TaskItem.model_validate(record)
            for record in generated_records or []
        ]
        if request.opportunity_id is None:
            return tasks_for_user(str(user["id"]))
        return generated_tasks

    # Only drop this user's tasks that belong to the *same* scope being
    # regenerated (same opportunity_id, including the "no opportunity"
    # bucket when opportunity_id is None). Previously the "no opportunity_id"
    # branch dropped every task the user owned across *all* opportunities,
    # silently wiping unrelated task lists on every general (non-file-ingested)
    # analysis. See Sprint 1 bugfix notes.
    with guarded("task-quota", str(user["id"])):
        retained_tasks = [
            task for task in tasks
            if not (
                task.user_id == user["id"]
                and task.opportunity_id == request.opportunity_id
            )
        ]

        # Base new ids on what survives this operation, not on tasks that
        # are about to be replaced -- otherwise regenerating the same scope
        # repeatedly would skip ever-larger blocks of ids for no reason.
        retained_owned_tasks = [
            task for task in retained_tasks if task.user_id == user["id"]
        ]
        next_id = max((task.id for task in retained_owned_tasks), default=0) + 1

        enforce_account_quota("task", len(retained_owned_tasks) + len(task_titles))

        for offset, title in enumerate(task_titles):
            generated_tasks.append(
                TaskItem(
                    id=next_id + offset,
                    user_id=str(user["id"]),
                    opportunity_id=request.opportunity_id,
                    title=title,
                    status="pending",
                )
            )

        tasks[:] = retained_tasks
        tasks.extend(generated_tasks)
        _persist_tasks(str(user["id"]))

    return [task for task in tasks if task.user_id == user["id"]] if request.opportunity_id is None else generated_tasks


@router.patch(
    "/{task_id}",
    response_model=TaskItem,
    status_code=status.HTTP_200_OK,
)
def update_task_status(
    task_id: int,
    update: TaskStatusUpdate,
    user: dict[str, str | bool] = Depends(get_current_user),
) -> TaskItem:
    if application_store is not None:
        updated = application_store.update_task_status(
            str(user["id"]),
            task_id,
            update.status,
        )
        if updated is not None:
            return TaskItem.model_validate(updated)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found.",
        )

    for index, task in enumerate(tasks):
        if task.id == task_id and task.user_id == user["id"]:
            updated_task = task.model_copy(update={"status": update.status})
            tasks[index] = updated_task
            _persist_tasks(str(user["id"]))
            return updated_task

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Task not found.",
    )


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    user: dict[str, str | bool] = Depends(get_current_user),
) -> None:
    if application_store is not None:
        if application_store.delete_task(str(user["id"]), task_id):
            return
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found.",
        )

    for index, task in enumerate(tasks):
        if task.id == task_id and task.user_id == user["id"]:
            tasks.pop(index)
            _persist_tasks(str(user["id"]))
            return

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Task not found.",
    )
