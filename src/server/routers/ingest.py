"""API 的 Ingest 端点（基于任务）。

摄取以后台任务方式运行，因此客户端可以离开页面，稍后通过
``GET /api/jobs`` / ``GET /api/jobs/{job_id}`` 恢复任务。
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from gitingest.utils.logger import get_logger
from server.job_store import job_store, spawn
from server.models import IngestRequest, JobCreatedResponse
from server.query_processor import process_query
from server.server_utils import limiter

logger = get_logger("ingest")

router = APIRouter()


async def _run_job(job_id: str, ingest_request: IngestRequest) -> None:
    """在后台运行任务的摄取流程并保存结果。"""
    logger.info("Job started [job_id={}] url={}", job_id, ingest_request.input_text)
    try:
        result = await process_query(
            input_text=ingest_request.input_text,
            max_file_size=ingest_request.max_file_size,
            pattern_type=ingest_request.pattern_type,
            pattern=ingest_request.pattern,
            token=ingest_request.token,
        )
        await job_store.update(job_id, status="done", result=result.model_dump())
        logger.info("Job completed [job_id={}] status=done", job_id)
    except Exception as exc:
        await job_store.update(job_id, status="error", error=str(exc))
        logger.exception("Job failed [job_id={}]", job_id)


async def create_ingest_job(
    request: Request, ingest_request: IngestRequest
) -> dict[str, str]:
    """创建一个后台摄取任务并启动它。

    由 JSON API（``/api/ingest``）和旧版表单回退路由共用，
    以保证两者行为一致。
    """
    uid = request.cookies.get("repoingest_uid", "")
    job = await job_store.create(
        uid,
        params={
            "repo_url": ingest_request.input_text,
            "max_file_size": ingest_request.max_file_size,
            "pattern_type": ingest_request.pattern_type.value,
            "pattern": ingest_request.pattern,
        },
    )
    spawn(_run_job(job["id"], ingest_request))
    return {"job_id": job["id"], "status": "running"}


@router.post("/api/ingest", response_model=JobCreatedResponse, status_code=202)
@limiter.limit("10/minute")
async def api_ingest(request: Request, ingest_request: IngestRequest) -> JSONResponse:
    """创建一个后台摄取任务并立即返回其 id。

    **该端点创建一个任务并返回带有 ``job_id`` 的 ``202`` 响应。**
    处理完成后（``status`` 变为 ``done`` 或 ``error``），可通过轮询
    ``GET /api/jobs/{job_id}`` 获取结果。
    """
    payload = await create_ingest_job(request, ingest_request)
    return JSONResponse(status_code=202, content=payload)
