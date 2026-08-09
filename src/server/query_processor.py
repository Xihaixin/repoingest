"""Process a query by parsing input, cloning a repository, and generating a summary."""

from typing import Optional

from gitingest.cloning import clone_repo, validate_github_token
from gitingest.ingestion import ingest_query
from gitingest.query_parsing import IngestionQuery, parse_query
from gitingest.utils.logger import get_logger
from server.models import IngestErrorResponse, IngestResponse, IngestSuccessResponse, PatternType
from server.server_config import MAX_DISPLAY_SIZE

logger = get_logger("query_processor")


def _build_query_details(
    url: str, max_file_size: int, pattern_type: str, pattern: str
) -> str:
    """Build a human-readable string describing a query's parameters.

    ``max_file_size`` is the file size slider position expressed in KB, so it
    is reported directly as ``<n>kb`` and the default (50) is omitted.
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
) -> IngestResponse:
    """
    Process a query by parsing input, cloning a repository, and generating a summary.

    Handle user input, process Git repository data, and prepare
    a response for rendering a template with the processed results or an error message.

    Parameters
    ----------
    input_text : str
        Input text provided by the user, typically a Git repository URL or slug.
    max_file_size : int
        Position of the slider, representing the maximum file size in the query.
    pattern_type : PatternType
        Type of pattern to use, either "include" or "exclude".
    pattern : str
        Pattern to include or exclude in the query, depending on the pattern type.
    token : str, optional
        GitHub personal access token (PAT) for accessing private repositories.

    Returns
    -------
    IngestResponse
        Success or error response containing the processed results.

    Raises
    ------
    ValueError
        If an invalid pattern type is provided.
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

    # Log success with token estimate if available
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