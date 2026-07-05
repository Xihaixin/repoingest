"""Utility functions for the server."""

import asyncio
import datetime
import math
import platform
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import Response
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from gitingest.config import TMP_BASE_PATH
from gitingest.utils.git_utils import ensure_git_installed
from gitingest.utils.logger import get_logger
from server.server_config import DELETE_REPO_AFTER

logger = get_logger("server_utils")

# Initialize a rate limiter
limiter = Limiter(key_func=get_remote_address)


async def rate_limit_exception_handler(request: Request, exc: Exception) -> Response:
    """
    Custom exception handler for rate-limiting errors.

    Parameters
    ----------
    request : Request
        The incoming HTTP request.
    exc : Exception
        The exception raised, expected to be RateLimitExceeded.

    Returns
    -------
    Response
        A response indicating that the rate limit has been exceeded.

    Raises
    ------
    exc
        If the exception is not a RateLimitExceeded error, it is re-raised.
    """
    if isinstance(exc, RateLimitExceeded):
        logger.warning("Rate limit exceeded for %s", request.client.host if request.client else "unknown")
        return _rate_limit_exceeded_handler(request, exc)
    raise exc


@asynccontextmanager
async def lifespan(_: FastAPI):
    """
    Lifecycle manager for handling startup and shutdown events for the FastAPI application.

    Parameters
    ----------
    _ : FastAPI
        The FastAPI application instance (unused).

    Yields
    -------
    None
        Yields control back to the FastAPI application while the background task runs.
    """
    logger.info("Starting server lifecycle: initializing Git check and cleanup task")
    task = asyncio.create_task(_remove_old_repositories())
    yield
    logger.info("Shutting down server lifecycle: cancelling cleanup task")
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def _remove_old_repositories():
    """
    Periodically remove old repository folders.

    Background task that runs periodically to clean up old repository directories.

    This task:
    - Scans the TMP_BASE_PATH directory every 60 seconds
    - Removes directories older than DELETE_REPO_AFTER seconds
    - Before deletion, logs repository URLs to history.txt if a matching .txt file exists
    - Handles errors gracefully if deletion fails

    The repository URL is extracted from the first .txt file in each directory,
    assuming the filename format: "owner-repository.txt"
    """
    while True:
        try:
            if not TMP_BASE_PATH.exists():
                await asyncio.sleep(60)
                continue

            current_time = time.time()

            for folder in TMP_BASE_PATH.iterdir():
                if not any(folder.iterdir()):
                    folder.rmdir()
                    logger.debug("Removed empty folder: %s", folder)
                    continue
                folder_stat = folder.stat()
                if platform.system() == "Windows":
                    folder_time = folder_stat.st_ctime
                else:
                    try:
                        folder_time = folder_stat.st_birthtime
                    except AttributeError:
                        folder_time = folder_stat.st_mtime

                if current_time - folder_time <= DELETE_REPO_AFTER:
                    continue

                await _process_folder(folder)

        except Exception as exc:
            logger.error("Error in _remove_old_repositories: %s", exc)

        await asyncio.sleep(60)


async def _process_folder(folder: Path) -> None:
    """
    Process a single folder for deletion and logging.

    Parameters
    ----------
    folder : Path
        The path to the folder to be processed.
    """
    # Try to log repository URL before deletion
    try:
        txt_files = [f for f in folder.iterdir() if f.suffix == ".txt"]

        if txt_files:
            filename = txt_files[0].stem
            if "-" in filename:
                owner, repo = filename.split("-", 1)
                repo_url = f"{owner}/{repo}"

                with open("history.txt", mode="a", encoding="utf-8") as f:
                    current_utc_time = datetime.datetime.now(datetime.timezone.utc).strftime(
                        "%Y-%m-%d %H:%M:%S.%f"
                    )[:-3]
                    f.write(f"[UTC]{current_utc_time} | {repo_url}\n")

                logger.info("Logged repository %s to history.txt before deletion", repo_url)

    except Exception as exc:
        logger.error("Error logging repository URL for %s: %s", folder, exc)

    # Delete the folder
    try:
        shutil.rmtree(folder)
        logger.info("Deleted old repository folder: %s", folder)
    except Exception as exc:
        logger.error("Error deleting %s: %s", folder, exc)


def log_slider_to_size(position: int) -> int:
    """
    Convert a slider position to a file size in bytes using a logarithmic scale.

    Parameters
    ----------
    position : int
        Slider position ranging from 0 to 500.

    Returns
    -------
    int
        File size in bytes corresponding to the slider position.
    """
    maxp = 500
    minv = math.log(1)
    maxv = math.log(102_400)
    return round(math.exp(minv + (maxv - minv) * pow(position / maxp, 1.5))) * 1024