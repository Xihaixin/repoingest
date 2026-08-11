"""Gitingest：一个用于从 Git 仓库中摄取数据的包。"""

from gitingest.entrypoint import ingest, ingest_async
from gitingest.ingestion import ingest_query
from gitingest.query_parsing import parse_query
from gitingest.cloning import clone_repo

__all__ = ["ingest_query", "clone_repo", "parse_query", "ingest", "ingest_async"]
