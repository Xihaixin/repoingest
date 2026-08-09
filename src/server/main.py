"""Main module for the FastAPI application."""
import os
import sys
import asyncio
import uvicorn
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from starlette.middleware.trustedhost import TrustedHostMiddleware

# ── Logging MUST be configured before any other import that uses it ──
from gitingest.utils.logger import setup_logging, get_logger

# Determine a sensible default log file path
_log_dir = Path(__file__).parent.parent / "logs"
_log_dir.mkdir(parents=True, exist_ok=True)
_default_log_file = str(_log_dir / "repoingest.log")

# Environment variable takes precedence, then fallback to default path
_log_file = os.getenv("REPOINGEST_LOG_FILE") or _default_log_file

setup_logging(log_file=_log_file)
logger = get_logger("server")

logger.info("Logging to file: {}", _log_file)

# Load environment variables from .env file
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

from server.routers import download, dynamic, index, ingest
from server.middleware import RequestLoggingMiddleware
from server.server_config import templates
from server.server_utils import lifespan, limiter, rate_limit_exception_handler


if sys.platform == "win32":
    logger.info("Setting ProactorEventLoopPolicy for Uvicorn server on Windows.")
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Initialize the FastAPI application with lifespan
app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter

# Register the custom exception handler for rate limits
app.add_exception_handler(RateLimitExceeded, rate_limit_exception_handler)


# Mount static files dynamically to serve CSS, JS, and other static assets
static_dir = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


# Fetch allowed host from the environment or use the default values
allowed_hosts = os.getenv("ALLOWED_HOSTS")
if allowed_hosts:
    allowed_hosts = allowed_hosts.split(",")
else:
    # Define the default allowed hosts for the application
    default_allowed_hosts = ["repoingest.top", "*.repoingest.top", "localhost", "127.0.0.1"]
    allowed_hosts = default_allowed_hosts

logger.debug("Allowed hosts: {}", allowed_hosts)

# Add middleware to enforce allowed hosts
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

# Request tracing: outermost middleware so every request (even rejected ones)
# is assigned a request_id and its lifecycle is logged
app.add_middleware(RequestLoggingMiddleware)


@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


@app.head("/")
async def head_root() -> HTMLResponse:
    """
    Respond to HTTP HEAD requests for the root URL.

    Mirrors the headers and status code of the index page.

    Returns
    -------
    HTMLResponse
        An empty HTML response with appropriate headers.
    """
    return HTMLResponse(content=None, headers={"content-type": "text/html; charset=utf-8"})


@app.get("/api/", response_class=HTMLResponse)
@app.get("/api", response_class=HTMLResponse)
async def api_docs(request: Request) -> HTMLResponse:
    """
    Render the API documentation page.

    Parameters
    ----------
    request : Request
        The incoming HTTP request.

    Returns
    -------
    HTMLResponse
        A rendered HTML page displaying API documentation.
    """
    return templates.TemplateResponse("api.jinja", {"request": request})


@app.get("/llms.txt")
async def llms() -> FileResponse:
    """
    Serve the `llms.txt` file for AI agents to read.

    Returns
    -------
    FileResponse
        The `llms.txt` file located in the static directory.
    """
    llms_txt_path = static_dir / "llms.txt"
    return FileResponse(str(llms_txt_path))


@app.get("/robots.txt")
async def robots() -> FileResponse:
    """
    Serve the `robots.txt` file to guide search engine crawlers.

    Returns
    -------
    FileResponse
        The `robots.txt` file located in the static directory.
    """
    robots_txt_path = static_dir / "robots.txt"
    return FileResponse(str(robots_txt_path))


# Include routers for module endpoints
app.include_router(index)
app.include_router(download)
app.include_router(ingest)
app.include_router(dynamic)


if __name__ == "__main__":
    port = int(os.getenv("REPOINGEST_PORT", 8000))
    host = os.getenv("REPOINGEST_HOST", "127.0.0.1")
    logger.info("Starting FastAPI server at http://{}:{}", host, port)

    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        reload=False,
        loop="asyncio",
        access_log=False,
        log_config=None,
    )

    server = uvicorn.Server(config=config)
    server.run()
    