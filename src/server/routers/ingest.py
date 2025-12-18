"""Ingest endpoint for the API."""

from typing import Union
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from gitingest.config import TMP_BASE_PATH
from server.models import IngestRequest
from server.routers_utils import COMMON_INGEST_RESPONSES, _perform_ingestion
from server.server_config import DEFAULT_FILE_SIZE_KB
from server.server_utils import limiter

router = APIRouter()

@router.post("/api/ingest", responses=COMMON_INGEST_RESPONSES)
@limiter.limit("10/minute")
async def api_ingest(
    request: Request,
    ingest_request: IngestRequest,
) -> JSONResponse:
    """Ingest a Git repository and return processed content.

    **This endpoint processes a Git repository by cloning it, analyzing its structure,**
    and returning a summary with the repository's content. The response includes
    file tree structure, processed content, and metadata about the ingestion.

    **Parameters**

    - **ingest_request** (`IngestRequest`): Pydantic model containing ingestion parameters

    **Returns**

    - **JSONResponse**: Success response with ingestion results or error response with appropriate HTTP status code

    """
    response = await _perform_ingestion(
        input_text=ingest_request.input_text,
        max_file_size=ingest_request.max_file_size,
        pattern_type=ingest_request.pattern_type.value,
        pattern=ingest_request.pattern,
        token=ingest_request.token,
    )

    return response
