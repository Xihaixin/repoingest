"""Ingest endpoint for the API (job-based).

Ingestion runs as a background task so the client can navigate away and later
resume the job via ``GET /api/jobs`` / ``GET /api/jobs/{job_id}``.
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
    """Run the ingestion for a job in the background and store the outcome."""
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
    """Create a background ingest job and start it.

    Shared by the JSON API (``/api/ingest``) and the legacy form-fallback
    route so both behave identically.
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
    """Create a background ingest job and return its id immediately.

    **This endpoint creates a job and returns ``202`` with a ``job_id``.**
    Poll ``GET /api/jobs/{job_id}`` to obtain the result once processing
    finishes (``status`` becomes ``done`` or ``error``).
    """
    payload = await create_ingest_job(request, ingest_request)
    return JSONResponse(status_code=202, content=payload)
