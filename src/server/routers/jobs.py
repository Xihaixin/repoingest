"""用于恢复后台摄取任务的任务状态端点。"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from server.job_store import job_store
from server.server_utils import limiter

router = APIRouter()


@router.get("/api/jobs", response_model=None)
@limiter.limit("60/minute")
async def list_jobs(request: Request) -> JSONResponse:
    """列出当前浏览器身份（uid）最近的摄取任务。

    仅返回元数据（不包含结果内容）；完整结果通过
    ``GET /api/jobs/{job_id}`` 按任务获取。
    """
    uid = request.cookies.get("repoingest_uid", "")
    jobs = await job_store.list_for_uid(uid, limit=10)
    return JSONResponse({"jobs": jobs})


@router.get("/api/jobs/{job_id}")
@limiter.limit("120/minute")
async def get_job(request: Request, job_id: str) -> JSONResponse:
    """返回任务的状态，并在任务完成时返回其完整结果。"""
    job = await job_store.get(job_id)
    if job is None:
        return JSONResponse({"error": "Job not found"}, status_code=404)
    return JSONResponse(
        {
            "id": job["id"],
            "status": job["status"],
            "result": job["result"],
            "error": job["error"],
            "created_at": job["created_at"],
            "updated_at": job["updated_at"],
        }
    )
