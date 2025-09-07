from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from uuid import UUID

from celery.utils.log import get_task_logger
from sqlalchemy.orm import Session

from .celery_app import celery
from ..utils.db import SessionLocal
from ..models.db_models import ReviewTask, ReviewResult, TaskStatus
from ..services.github_service import GitHubClient
from ..services.static_checks import run_static_checks
from ..models.schema import ReviewResults
from ..agents.code_reviewer import build_agent, run_agent_review

logger = get_task_logger(__name__)

@celery.task(bind=True, name="app.tasks.task.analyze_pr")
def analyze_pr(self, task_id: str, github_token: str | None = None):
    """Celery task entrypoint. Accepts DB task id, performs analysis, stores results."""
    session: Session = SessionLocal()
    started_at = datetime.now(timezone.utc)

    logger.info(
        "task.analyze_pr.start",
        extra={"task_id": task_id, "github_token_present": bool(github_token)},
    )

    try:
        task: ReviewTask | None = session.get(ReviewTask, UUID(task_id))
        if not task:
            logger.error("task.analyze_pr.not_found", extra={"task_id": task_id})
            self.update_state(state="FAILURE", meta={"error": "Task not found"})
            return

        # Mark processing
        task.status = TaskStatus.processing
        task.started_at = started_at
        session.commit()

        # Fetch PR data
        gh = GitHubClient(token=github_token)
        t0 = time.perf_counter()
        files = asyncio.run(gh.list_pr_files(task.repo_url, task.pr_number))
        patch = asyncio.run(gh.get_pr_patch(task.repo_url, task.pr_number))
        fetch_ms = int((time.perf_counter() - t0) * 1000)

        logger.info(
            "task.analyze_pr.github_fetched",
            extra={
                "task_id": task_id,
                "repo_url": task.repo_url,
                "pr_number": task.pr_number,
                "files_count": len(files),
                "patch_len": len(patch),
                "duration_ms": fetch_ms,
            },
        )

        # Static checks (per-file) – FIXED indentation so each file is processed
        static_hints: dict[str, list[dict]] = {}
        hint_total = 0
        for f in files:
            name = f.get("filename")
            file_patch: str | None = f.get("patch")
            if not file_patch:
                continue

            added_lines = []
            for line in file_patch.splitlines():
                if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
                    continue
                if line.startswith("+") and not line.startswith("+++"):
                    added_lines.append(line[1:])

            content_for_check = "\n".join(added_lines)
            hints = run_static_checks(name, content_for_check)
            if hints:
                static_hints[name] = hints
                hint_total += len(hints)

        logger.info(
            "task.analyze_pr.static_checks_done",
            extra={"task_id": task_id, "hint_files": len(static_hints), "hint_total": hint_total},
        )

        # Agent review
        agent = build_agent()
        t1 = time.perf_counter()
        payload = run_agent_review(agent, patch, files, static_hints)
        agent_ms = int((time.perf_counter() - t1) * 1000)

        # Validate/normalize with Pydantic
        model = ReviewResults.model_validate(payload)
        payload = model.model_dump()

        # Persist results
        session.merge(ReviewResult(task_id=task.id, results_json=payload))
        task.status = TaskStatus.completed
        task.completed_at = datetime.now(timezone.utc)
        session.commit()

        # Log summary
        summary = payload.get("summary", {})
        logger.info(
            "task.analyze_pr.completed",
            extra={
                "task_id": task_id,
                "total_files": summary.get("total_files"),
                "total_issues": summary.get("total_issues"),
                "critical_issues": summary.get("critical_issues"),
                "github_ms": fetch_ms,
                "agent_ms": agent_ms,
                "elapsed_ms": int((time.perf_counter() - t0) * 1000),
            },
        )
        return {"status": task.status}

    except Exception as e:
        session.rollback()
        try:
            task = session.get(ReviewTask, UUID(task_id))
            if task:
                task.status = TaskStatus.failed
                task.error = str(e)
                session.commit()
        finally:
            logger.exception(
                "task.analyze_pr.failed",
                extra={"task_id": task_id},
            )
            self.update_state(state="FAILURE", meta={"error": str(e)})
            raise
    finally:
        session.close()
