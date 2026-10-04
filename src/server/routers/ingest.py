"""API 的 Ingest 端点（基于任务）。

摄取以后台任务方式运行，因此客户端可以离开页面，稍后通过
``GET /api/jobs`` / ``GET /api/jobs/{job_id}`` 恢复任务。
"""

import re
import time
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from gitingest.utils.logger import get_logger
from server import analytics
from server.job_store import job_store, spawn
from server.models import IngestRequest, JobCreatedResponse
from server.query_processor import process_query
from server.routers_utils import require_uid
from server.server_utils import limiter

logger = get_logger("ingest")

router = APIRouter()

_FILE_COUNT_RE = re.compile(r"Files analyzed:(\d+)")
_TOKEN_ESTIMATE_RE = re.compile(r"Estimated tokens:([\d.]+[kM]?)")


def _repo_host(value: str) -> str:
    """尽力从仓库输入中提取主机名（绝不上报完整 URL）。"""
    if not value:
        return "unknown"

    text = str(value).strip()
    ssh = re.match(r"^[^@]+@([^:/]+)[:/]", text)
    if ssh:
        return ssh.group(1)

    if "://" in text:
        try:
            return urlparse(text).hostname or "unknown"
        except ValueError:
            return "unknown"

    first = text.split("/")[0]
    return first if "." in first else "unknown"


def _parse_token_estimate(raw: str) -> int:
    """把 ``1.2k`` / ``1.2M`` / ``123`` 形式的估算值转为整数。"""
    multiplier = 1
    if raw.endswith("M"):
        multiplier = 1_000_000
        raw = raw[:-1]
    elif raw.endswith("k"):
        multiplier = 1_000
        raw = raw[:-1]
    try:
        return int(float(raw) * multiplier)
    except ValueError:
        return 0


def _summary_metrics(summary: str) -> dict[str, Any]:
    """从摄取摘要中解析文件数与 token 估算值。"""
    metrics: dict[str, Any] = {}

    file_match = _FILE_COUNT_RE.search(summary)
    if file_match:
        metrics["file_count"] = int(file_match.group(1))

    token_match = _TOKEN_ESTIMATE_RE.search(summary)
    if token_match:
        metrics["token_count"] = _parse_token_estimate(token_match.group(1))

    return metrics


def _ingest_base_properties(job_id: str, ingest_request: IngestRequest) -> dict[str, Any]:
    """构建摄取任务共用的分析属性。"""
    return {
        "job_id": job_id,
        "repo_host": _repo_host(ingest_request.input_text),
        "pattern_type": ingest_request.pattern_type.value,
        "max_file_size_kb": ingest_request.max_file_size,
        "has_token": bool(ingest_request.token),
    }


async def _run_job(job_id: str, uid: str, ingest_request: IngestRequest) -> None:
    """在后台运行任务的摄取流程并保存结果。"""
    logger.info("Job started [job_id={}] url={}", job_id, ingest_request.input_text)
    started = time.perf_counter()
    base_props = _ingest_base_properties(job_id, ingest_request)
    analytics.capture(uid, "ingest_started", base_props)

    try:
        result = await process_query(
            input_text=ingest_request.input_text,
            max_file_size=ingest_request.max_file_size,
            pattern_type=ingest_request.pattern_type,
            pattern=ingest_request.pattern,
            token=ingest_request.token,
        )
        await job_store.update(job_id, status="done", result=result.model_dump())

        completed_props: dict[str, Any] = {
            "job_id": job_id,
            "repo_host": base_props["repo_host"],
            "duration_ms": round((time.perf_counter() - started) * 1000),
        }
        completed_props.update(_summary_metrics(result.summary))
        analytics.capture(uid, "ingest_completed", completed_props)

        logger.info("Job completed [job_id={}] status=done", job_id)
    except Exception as exc:
        await job_store.update(job_id, status="error", error=str(exc))
        analytics.capture(
            uid,
            "ingest_failed",
            {
                "job_id": job_id,
                "repo_host": base_props["repo_host"],
                "duration_ms": round((time.perf_counter() - started) * 1000),
                "error_type": type(exc).__name__,
            },
        )
        logger.exception("Job failed [job_id={}]", job_id)


async def create_ingest_job(uid: str, ingest_request: IngestRequest) -> dict[str, str]:
    """创建一个后台摄取任务并启动它。

    由 JSON API（``/api/ingest``）和旧版表单回退路由共用，
    以保证两者行为一致。``uid`` 由 ``require_uid`` 依赖校验后传入。
    """
    job = await job_store.create(
        uid,
        params={
            "repo_url": ingest_request.input_text,
            "max_file_size": ingest_request.max_file_size,
            "pattern_type": ingest_request.pattern_type.value,
            "pattern": ingest_request.pattern,
        },
    )
    spawn(_run_job(job["id"], uid, ingest_request))
    return {"job_id": job["id"], "status": "running"}


@router.post("/api/ingest", response_model=JobCreatedResponse, status_code=202)
@limiter.limit("10/minute")
async def api_ingest(
    request: Request,
    ingest_request: IngestRequest,
    uid: str = Depends(require_uid),
) -> JSONResponse:
    """创建一个后台摄取任务并立即返回其 id。

    **该端点创建一个任务并返回带有 ``job_id`` 的 ``202`` 响应。**
    处理完成后（``status`` 变为 ``done`` 或 ``error``），可通过轮询
    ``GET /api/jobs/{job_id}`` 获取结果。
    """
    payload = await create_ingest_job(uid, ingest_request)
    return JSONResponse(status_code=202, content=payload)
