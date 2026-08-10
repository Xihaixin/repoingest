"""该模块包含 FastAPI 应用的路由。"""

from server.routers.download import router as download
from server.routers.dynamic import router as dynamic
from server.routers.index import router as index
from server.routers.ingest import router as ingest
from server.routers.jobs import router as jobs

__all__ = ["download", "dynamic", "index", "ingest", "jobs"]
