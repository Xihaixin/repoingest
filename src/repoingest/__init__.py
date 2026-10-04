"""repoingest：一个用于从 Git 仓库中摄取数据的包。"""

__version__ = "0.1.0"

from repoingest.entrypoint import ingest, ingest_async
from repoingest.ingestion import ingest_query
from repoingest.query_parsing import parse_query
from repoingest.cloning import clone_repo

__all__ = [
    "__version__",
    "ingest_query",
    "clone_repo",
    "parse_query",
    "ingest",
    "ingest_async",
]
