"""用于异步摄入任务的内存任务存储。

摄入在后台运行，因此客户端可以离开页面，之后再恢复（轮询）任务。
结果包含仓库内容，因此任务会在有界的保留窗口内、并且按浏览器身份
以有界的数量保留。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Awaitable, Optional

from gitingest.utils.logger import get_logger

logger = get_logger("job_store")

# 已完成任务的保留窗口（秒）。
JOB_TTL_SECONDS = 2 * 60 * 60  # 2 hours

# 每个 uid 保留的最大任务数（限制内存占用）。
MAX_JOBS_PER_UID = 20


class JobStore:
    """线程安全的摄入任务内存注册表。"""

    def __init__(self, ttl_seconds: int = JOB_TTL_SECONDS) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._ttl = ttl_seconds

    async def create(self, uid: str, params: dict[str, Any]) -> dict[str, Any]:
        """创建一个 ``running`` 任务并返回它。"""
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
        """返回一个任务或 ``None``。"""
        async with self._lock:
            return self._jobs.get(job_id)

    async def update(self, job_id: str, **fields: Any) -> None:
        """就地更新任务的字段（如果任务未知则为空操作）。"""
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.update(fields)
            job["updated_at"] = time.time()

    async def list_for_uid(self, uid: str, limit: int = 10) -> list[dict[str, Any]]:
        """返回某个 uid 的最近任务摘要（仅元数据），最新在前。"""
        async with self._lock:
            jobs = [
                self._summary(job) for job in self._jobs.values() if job["uid"] == uid
            ]
            jobs.sort(key=lambda j: j["created_at"], reverse=True)
            return jobs[:limit]

    async def cleanup(self) -> int:
        """移除过期任务并限制每个 uid 的历史数量。返回被移除的数量。"""
        async with self._lock:
            now = time.time()
            to_remove = [
                job_id
                for job_id, job in self._jobs.items()
                if now - job["created_at"] > self._ttl
            ]

            # 每个 uid 仅保留最新的 MAX_JOBS_PER_UID 个任务。
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


# ── 后台任务跟踪 ───────────────────────────────────────
_pending_tasks: set[asyncio.Task] = set()


def spawn(coro: Awaitable[None]) -> asyncio.Task:
    """在事件循环上调度 ``coro`` 并跟踪它以便在关闭时处理。"""
    task = asyncio.create_task(coro)
    _pending_tasks.add(task)
    task.add_done_callback(_pending_tasks.discard)
    return task


def cancel_pending() -> None:
    """取消任何进行中的后台摄入任务（在关闭时使用）。"""
    for task in list(_pending_tasks):
        task.cancel()


async def cleanup_loop(interval: float = 300.0) -> None:
    """定期清理过期 / 多余的任务。"""
    while True:
        await asyncio.sleep(interval)
        try:
            removed = await job_store.cleanup()
            if removed:
                logger.info("Job cleanup removed {} expired/overflow jobs", removed)
        except Exception:
            logger.exception("Job cleanup failed")
