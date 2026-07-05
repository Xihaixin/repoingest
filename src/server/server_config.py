"""Configuration for the server."""
import os
from pathlib import Path
from typing import Dict, List

from fastapi.templating import Jinja2Templates

MAX_DISPLAY_SIZE : int = 300_000
DEFAULT_FILE_SIZE_KB: int = 5 * 1024  # 5 mb
DELETE_REPO_AFTER: int = 5 * 24 * 60 * 60  # 5 days in seconds
MAX_FILE_SIZE_KB: int = 100 * 1024  # 100 mb

EXAMPLE_REPOS: List[Dict[str, str]] = [
    {"name": "Gitingest", "url": "https://github.com/cyclotruc/gitingest"},
    {"name": "FastAPI", "url": "https://github.com/tiangolo/fastapi"},
    {"name": "Flask", "url": "https://github.com/pallets/flask"},
    {"name": "Excalidraw", "url": "https://github.com/excalidraw/excalidraw"},
    {"name": "ApiAnalytics", "url": "https://github.com/tom-draper/api-analytics"},
]

# Version and repository configuration
APP_REPOSITORY = os.getenv("APP_REPOSITORY", "https://github.com/coderamp-labs/gitingest")
APP_VERSION = os.getenv("APP_VERSION", "0.1.0")
APP_VERSION_URL = os.getenv("APP_VERSION_URL", "https://github.com/coderamp-labs/gitingest")

def get_version_info() -> dict[str, str]:
    """Get version information including display version and link.

    Returns
    -------
    dict[str, str]
        Dictionary containing 'version' and 'version_link' keys.

    """
    # Use pre-computed values from GitHub Actions
    display_version = APP_VERSION
    version_link = APP_VERSION_URL

    # Fallback to repository root if no URL is provided
    if version_link == APP_REPOSITORY or not version_link:
        version_link = f"{APP_REPOSITORY.rstrip('/')}/tree/main"

    return {
        "version": display_version,
        "version_link": version_link,
    }

templates_dir = Path(__file__).parent / 'templates'
templates = Jinja2Templates(directory=str(templates_dir))