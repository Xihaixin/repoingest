"""In-memory job store for asynchronous ingest tasks.

Ingestion runs in the background so the client can navigate away and later
resume (poll) the job.  Results contain repository content, so jobs are kept
for a bounded retention window and a bounded count per browser identity.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Awaitable, Optional

from gitingest.utils.logger import get_logger

logger = get_logger("job_store")

# Retention window for finished jobs (seconds).
JOB_TTL_SECONDS = 2 * 60 * 60  # 2 hours

# Maximum number of jobs kept per uid (bounds memory).
MAX_JOBS_PER_UID = 20


class JobStore:
    """Thread-safe in-memory registry of ingest jobs."""

    def __init__(self, ttl_seconds: int = JOB_TTL_SECONDS) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._ttl = ttl_seconds

    async def create(self, uid: str, params: dict[str, Any]) -> dict[str, Any]:
        """Create a ``running`` job and return it."""
        async with self._lock:
            now = time.time()
            job: dict[str, Any] = {
                "id": uuid.uuid4().hex,
                "uid": uid,
                "status": "running",
                "result": None,
                "error": None,
                "params": params,
                "created_at": now,
                "updated_at": now,
            }
            self._jobs[job["id"]] = job
            return job

    async def get(self, job_id: str) -> Optional[dict[str, Any]]:
        """Return a job or ``None``."""
        async with self._lock:
            return self._jobs.get(job_id)

    async def update(self, job_id: str, **fields: Any) -> None:
        """Update a job's fields in place (no-op if the job is unknown)."""
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.update(fields)
            job["updated_at"] = time.time()

    async def list_for_uid(self, uid: str, limit: int = 10) -> list[dict[str, Any]]:
        """Return recent job summaries (metadata only) for a uid, newest first."""
        async with self._lock:
            jobs = [
                self._summary(job) for job in self._jobs.values() if job["uid"] == uid
            ]
            jobs.sort(key=lambda j: j["created_at"], reverse=True)
            return jobs[:limit]

    async def cleanup(self) -> int:
        """Remove expired jobs and cap per-uid history. Returns removed count."""
        async with self._lock:
            now = time.time()
            to_remove = [
                job_id
                for job_id, job in self._jobs.items()
                if now - job["created_at"] > self._ttl
            ]

            # Keep only the newest MAX_JOBS_PER_UID jobs per uid.
            by_uid: dict[str, list[tuple[float, str]]] = {}
            for job_id, job in self._jobs.items():
                if job_id not in to_remove:
                    by_uid.setdefault(job["uid"], []).append(
                        (job["created_at"], job_id)
                    )
            for items in by_uid.values():
                items.sort(reverse=True)
                to_remove.extend(job_id for _, job_id in items[MAX_JOBS_PER_UID:])

            for job_id in to_remove:
                self._jobs.pop(job_id, None)
            return len(to_remove)

    @staticmethod
    def _summary(job: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": job["id"],
            "status": job["status"],
            "repo_url": job["params"].get(
                "repo_url", job["params"].get("input_text", "")
            ),
            "error": job["error"],
            "created_at": job["created_at"],
            "updated_at": job["updated_at"],
        }


job_store = JobStore()


# ── Background task tracking ───────────────────────────────────────
_pending_tasks: set[asyncio.Task] = set()


def spawn(coro: Awaitable[None]) -> asyncio.Task:
    """Schedule ``coro`` on the event loop and track it for shutdown."""
    task = asyncio.create_task(coro)
    _pending_tasks.add(task)
    task.add_done_callback(_pending_tasks.discard)
    return task


def cancel_pending() -> None:
    """Cancel any in-flight background ingest tasks (used on shutdown)."""
    for task in list(_pending_tasks):
        task.cancel()


async def cleanup_loop(interval: float = 300.0) -> None:
    """Periodically prune expired / excess jobs."""
    while True:
        await asyncio.sleep(interval)
        try:
            removed = await job_store.cleanup()
            if removed:
                logger.info("Job cleanup removed {} expired/overflow jobs", removed)
        except Exception:
            logger.exception("Job cleanup failed")
