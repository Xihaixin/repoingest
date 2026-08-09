"""Job status endpoints for resuming background ingest tasks."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from server.job_store import job_store
from server.server_utils import limiter

router = APIRouter()


@router.get("/api/jobs", response_model=None)
@limiter.limit("60/minute")
async def list_jobs(request: Request) -> JSONResponse:
    """List recent ingest jobs for the current browser identity (uid).

    Returns metadata only (no result content); the full result is fetched per
    job via ``GET /api/jobs/{job_id}``.
    """
    uid = request.cookies.get("repoingest_uid", "")
    jobs = await job_store.list_for_uid(uid, limit=10)
    return JSONResponse({"jobs": jobs})


@router.get("/api/jobs/{job_id}")
@limiter.limit("120/minute")
async def get_job(request: Request, job_id: str) -> JSONResponse:
    """Return the status and, when finished, the full result of a job."""
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
