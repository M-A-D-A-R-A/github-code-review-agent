from __future__ import annotations
import fastapi
from ..config import get_settings


from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import JSONResponse
from uuid import UUID

router = fastapi.APIRouter(prefix="/github")

from ..models.schema import AnalyzePRRequest, AnalyzePRResponse, StatusResponse, ResultsResponse
from ..utils.db import session_scope

from ..tasks.celery_app import celery

from ..models.db_models import ReviewTask,TaskStatus, ReviewResult

@router.post("/analyze-pr", response_model=AnalyzePRResponse)
def analyze_pr(req: AnalyzePRRequest):
# Create DB task
    with session_scope() as s:
        task = ReviewTask(repo_url=str(req.repo_url), pr_number=req.pr_number)
        s.add(task)
        s.flush()
        # Enqueue Celery job
        async_result = celery.send_task("app.tasks.task.analyze_pr", args=[str(task.id), req.github_token])
        task.celery_task_id = async_result.id
        s.add(task)
        return AnalyzePRResponse(task_id=task.id, status=task.status.value)


@router.get("/status/{task_id}", response_model=StatusResponse)
def get_status(task_id: UUID):
    with session_scope() as s:
        task = s.get(ReviewTask, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return StatusResponse(task_id=task.id, status=task.status.value, error=task.error)


@router.get("/results/{task_id}", response_model=ResultsResponse)
def get_results(task_id: UUID):
    with session_scope() as s:
        task = s.get(ReviewTask, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        if task.status != TaskStatus.completed:
            return ResultsResponse(task_id=task.id, status=task.status.value, results=None)
        res = s.get(ReviewResult, task_id)
        if not res:
            raise HTTPException(status_code=404, detail="Results not found")
        return JSONResponse(
            status_code=200,
            content={
            "task_id": str(task.id),
            "status": task.status.value,
            "results": res.results_json,
            },
        )