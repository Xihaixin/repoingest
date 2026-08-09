"""This module defines the FastAPI router for the home / landing pages."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from server.i18n import LANGUAGES
from server.server_config import EXAMPLE_REPOS, render_template, get_version_info

router = APIRouter()


def _safe_next(next_url: str) -> str:
    """Return a safe local redirect target (prevents open redirects)."""
    if next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return "/"


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def home(request: Request) -> HTMLResponse:
    """
    Render the landing page that introduces the project to new visitors.

    Parameters
    ----------
    request : Request
        The incoming HTTP request.

    Returns
    -------
    HTMLResponse
        The rendered landing page.
    """
    context = {
        "examples": EXAMPLE_REPOS,
    }
    context.update(get_version_info())

    return render_template("home.jinja", request, **context)


@router.get("/app", response_class=HTMLResponse, include_in_schema=False)
async def app_page(request: Request) -> HTMLResponse:
    """
    Render the Ingest tool (form + results).

    Parameters
    ----------
    request : Request
        The incoming HTTP request.

    Returns
    -------
    HTMLResponse
        The rendered tool page.
    """
    context = {
        "examples": EXAMPLE_REPOS,
        "default_max_file_size": 243,
        "repo_url": request.query_params.get("repo", ""),
    }
    context.update(get_version_info())

    return render_template("index.jinja", request, **context)


@router.get("/lang/{code}", include_in_schema=False)
async def switch_language(request: Request, code: str) -> RedirectResponse:
    """
    Persist the chosen language in a cookie and redirect back to the caller.

    Parameters
    ----------
    request : Request
        The incoming HTTP request.
    code : str
        One of the supported language codes (e.g. ``zh-CN``, ``en``).

    Returns
    -------
    RedirectResponse
        A redirect back to ``next`` (or ``/``) with the language cookie set.
    """
    if code not in LANGUAGES:
        code = "en"

    next_url = _safe_next(request.query_params.get("next", "/"))
    response = RedirectResponse(url=next_url, status_code=302)
    response.set_cookie(
        key="lang",
        value=code,
        path="/",
        httponly=True,
        samesite="lax",
        max_age=365 * 24 * 3600,
    )
    return response
