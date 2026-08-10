"""This module defines the dynamic router for handling dynamic path requests."""

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse

from server.models import IngestRequest, PatternType
from server.routers.ingest import create_ingest_job
from server.server_config import render_template
from server.server_utils import limiter

router = APIRouter()


@router.get("/{full_path:path}")
async def catch_all(request: Request, full_path: str) -> HTMLResponse:
    """
    Render a page with a Git URL based on the provided path.

    This endpoint catches all GET requests with a dynamic path, constructs a Git URL
    using the `full_path` parameter, and renders the `git.jinja` template with that URL.

    Parameters
    ----------
    request : Request
        The incoming request object, which provides context for rendering the response.
    full_path : str
        The full path extracted from the URL, which is used to build the Git URL.

    Returns
    -------
    HTMLResponse
        An HTML response containing the rendered template, with the Git URL
        and other default parameters such as loading state and file size.
    """
    return render_template(
        "git.jinja",
        request,
        repo_url=full_path,
        loading=True,
        default_file_size=243,
    )


@router.post("/{full_path:path}")
@limiter.limit("10/minute")
async def process_catch_all(
    request: Request,
    input_text: str = Form(...),
    max_file_size: int = Form(...),
    pattern_type: PatternType = Form(...),
    pattern: str = Form(...),
    token: str = Form(""),
) -> JSONResponse:
    """
    Process the form submission with user input for query parameters.

    This endpoint catches native (no-JavaScript) form submissions and forwards
    them to the same background job pipeline as ``POST /api/ingest``, returning
    the identical ``202`` response with a ``job_id``.

    Parameters
    ----------
    request : Request
        The incoming request object, which provides context for rendering the response.
    input_text : str
        The input text provided by the user for processing, by default taken from the form.
    max_file_size : int
        The maximum allowed file size for the input, specified by the user.
    pattern_type : PatternType
        The type of pattern used for the query, specified by the user.
    pattern : str
        The pattern string used in the query, specified by the user.
    token : str
        Optional GitHub personal access token for private repositories.

    Returns
    -------
    JSONResponse
        A ``202`` response with ``{"job_id": ..., "status": "running"}``,
        identical to the ``/api/ingest`` endpoint.
    """
    ingest_request = IngestRequest(
        input_text=input_text,
        max_file_size=max_file_size,
        pattern_type=pattern_type,
        pattern=pattern,
        token=token,
    )
    payload = await create_ingest_job(request, ingest_request)
    return JSONResponse(status_code=202, content=payload)
