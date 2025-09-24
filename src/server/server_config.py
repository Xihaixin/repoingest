"""Configuration for the server."""
from pathlib import Path
from typing import Dict, List

from fastapi.templating import Jinja2Templates

MAX_DISPLAY_SIZE : int = 300_000
DELETE_REPO_AFITER: int = 60 * 60  # In seconds

EXAMPLE_REPOS: List[Dict[str, str]] = [
    {"name": "Gitingest", "url": "https://github.com/cyclotruc/gitingest"},
    {"name": "FastAPI", "url": "https://github.com/tiangolo/fastapi"},
    {"name": "Flask", "url": "https://github.com/pallets/flask"},
    {"name": "Excalidraw", "url": "https://github.com/excalidraw/excalidraw"},
    {"name": "ApiAnalytics", "url": "https://github.com/tom-draper/api-analytics"},
]

templates_dir = Path(__file__).parent / 'templates'
templates = Jinja2Templates(directory=str(templates_dir))