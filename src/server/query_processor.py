"""通过解析输入、克隆仓库并生成摘要来处理查询。"""

from typing import Optional

from repoingest.cloning import clone_repo, validate_github_token
from repoingest.ingestion import ingest_query
from repoingest.query_parsing import IngestionQuery, parse_query
from repoingest.utils.logger import get_logger
from server.models import IngestErrorResponse, IngestResponse, IngestSuccessResponse, PatternType
from server.server_config import MAX_DISPLAY_SIZE

logger = get_logger("query_processor")


def _build_query_details(
    url: str, max_file_size: int, pattern_type: str, pattern: str
) -> str:
    """构建描述查询参数的人类可读字符串。

    ``max_file_size`` 是以 KB 表示的文件大小滑块位置，因此直接以
    ``<n>kb`` 形式报告，默认值（50）会被省略。
    """
    parts = [f"url={url}"]
    if max_file_size != 50:
        parts.append(f"size={max_file_size}kb")
    if pattern and pattern_type == "include":
        parts.append(f"include={pattern}")
    elif pattern and pattern_type == "exclude":
        parts.append(f"exclude={pattern}")
    return " | ".join(parts)


async def process_query(
    input_text: str,
    max_file_size: int,
    pattern_type: PatternType,
    pattern: str = "",
    token: Optional[str] = None,
    is_index: bool = False,
) -> IngestResponse:
    """
    通过解析输入、克隆仓库并生成摘要来处理查询。

    处理用户输入、处理 Git 仓库数据，并准备
    用于渲染模板的响应，其中包含处理结果或错误信息。

    参数
    ----------
    input_text : str
        用户提供的输入文本，通常是 Git 仓库 URL 或 slug。
    max_file_size : int
        滑块位置，表示查询中的最大文件大小。
    pattern_type : PatternType
        要使用的模式类型，为 "include" 或 "exclude"。
    pattern : str
        查询中包含或排除的模式，取决于模式类型。
    token : str, optional
        用于访问私有仓库的 GitHub 个人访问令牌（PAT）。

    返回
    -------
    IngestResponse
        包含处理结果的成功或错误响应。

    异常
    ------
    ValueError
        如果提供了无效的模式类型。
    """
    if token:
        validate_github_token(token)

    if pattern_type == "include":
        include_patterns = pattern
        exclude_patterns = None
    elif pattern_type == "exclude":
        exclude_patterns = pattern
        include_patterns = None
    else:
        raise ValueError(f"Invalid pattern type: {pattern_type}")

    query: Optional[IngestionQuery] = None
    short_repo_url = ""
    content = ""

    try:
        query = await parse_query(
            source=input_text,
            max_file_size=max_file_size,
            from_web=True,
            include_patterns=include_patterns,
            ignore_patterns=exclude_patterns,
        )
        if not query.url:
            raise ValueError("The 'url' parameter is required.")

        clone_config = query.extract_clone_config()
        await clone_repo(clone_config)

        short_repo_url = f"{query.user_name}/{query.repo_name}"

        summary, tree, content = ingest_query(query)
        with open(f"{clone_config.local_path}.txt", "w", encoding="utf-8") as f:
            f.write(tree + "\n" + content)

    except Exception as exc:
        query_url = (query.url if query and query.url else input_text)
        details = _build_query_details(str(query_url), max_file_size, pattern_type, pattern)
        logger.exception("Query failed [{}]: {}", details, exc)
        raise

    if len(content) > MAX_DISPLAY_SIZE:
        logger.warning(
            "Content cropped for {}: {} -> {} characters (full digest available via download)",
            query.url or input_text,
            len(content),
            MAX_DISPLAY_SIZE,
        )
        content = (
            f"(Files content cropped to {int(MAX_DISPLAY_SIZE / 1_000)}k characters,"
            "download full ingest to see more)\n" + content[:MAX_DISPLAY_SIZE]
        )

    # 在可用时记录成功日志并附带 token 估算值
    try:
        estimated_tokens = summary[summary.index("Estimated tokens:") + len("Estimated tokens:") :]
    except ValueError:
        estimated_tokens = "unknown"
    details = _build_query_details(query.url or input_text, max_file_size, pattern_type, pattern)
    logger.info("Query succeeded [{}] | tokens={}", details, str(estimated_tokens).strip())

    return IngestSuccessResponse(
        repo_url=input_text,
        short_repo_url=short_repo_url,
        summary=summary,
        tree=tree,
        content=content,
        default_max_file_size=max_file_size,
        pattern_type=pattern_type,
        pattern=pattern,
    )