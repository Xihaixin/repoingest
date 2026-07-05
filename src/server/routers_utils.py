"""Utility functions for the ingest endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import status
from fastapi.responses import JSONResponse

from gitingest.utils.logger import get_logger
from server.models import IngestErrorResponse, IngestSuccessResponse, PatternType
from server.query_processor import process_query

logger = get_logger("routers_utils")

COMMON_INGEST_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_200_OK: {"model": IngestSuccessResponse, "description": "Successful ingestion"},
    status.HTTP_400_BAD_REQUEST: {"model": IngestErrorResponse, "description": "Bad request or processing error"},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": IngestErrorResponse, "description": "Internal server error"},
}


async def _perform_ingestion(
    input_text: str,
    max_file_size: int,
    pattern_type: str,
    pattern: str,
    token: str | None,
) -> JSONResponse:
    """Run ``process_query`` and wrap the result in a ``FastAPI`` ``JSONResponse``.

    Consolidates error handling shared by the ``POST`` and ``GET`` ingest endpoints.
    """
    try:
        pattern_type = PatternType(pattern_type)

        result = await process_query(
            input_text=input_text,
            max_file_size=max_file_size,
            pattern_type=pattern_type,
            pattern=pattern,
            token=token,
        )

        if isinstance(result, IngestErrorResponse):
            logger.warning("Ingestion returned error for input='%s': %s", input_text, result.model_dump().get("error"))
            return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=result.model_dump())

        logger.info("Ingestion succeeded for input='%s'", input_text)
        return JSONResponse(status_code=status.HTTP_200_OK, content=result.model_dump())

    except ValueError as ve:
        logger.warning("Validation error for input='%s': %s", input_text, ve)
        error_response = IngestErrorResponse(error=f"Validation error: {ve!s}")
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=error_response.model_dump())

    except Exception as exc:
        logger.error("Internal server error for input='%s': %s", input_text, exc)
        error_response = IngestErrorResponse(error=f"Internal server error: {exc!s}")
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_response.model_dump())
