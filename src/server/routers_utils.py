"""Utilities previously shared by the ingest endpoints.

Ingestion now runs as background jobs (see ``server.routers.ingest`` and
``server.routers.jobs``); this module is kept for its logger namespace only.
"""

from gitingest.utils.logger import get_logger

logger = get_logger("routers_utils")
