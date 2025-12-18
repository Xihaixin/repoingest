"""Process a query by parsing input, cloning a repository, and generating a summary."""

from gitingest.cloning import clone_repo
from gitingest.ingestion import ingest_query
from gitingest.query_parsing import IngestionQuery, parse_query
from server.server_config import MAX_DISPLAY_SIZE
from server.server_utils import Colors
from gitingest.cloning import validate_github_token
from server.models import IngestErrorResponse, IngestResponse, IngestSuccessResponse, PatternType

async def process_query(
        input_text: str,
        max_file_size: int,
        pattern_type: PatternType,
        pattern: str = "",
        token: str | None = None,
) -> IngestResponse:
    """
    Process a query by parsing input, cloning a repository, and generating a summary.

    Handle user input, process Git repository data, and prepare
    a response for rendering a template with the processed results or an error message.

    Parameters
    ----------
    request : Request
        The HTTP request object.
    input_text : str
        Input text provided by the user, typically a Git repository URL or slug.
    slider_position : int
        Position of the slider, representing the maximum file size in the query.
    pattern_type : str
        Type of pattern to use, either "include" or "exclude" (default is "exclude").
    pattern : str
        Pattern to include or exclude in the query, depending on the pattern type.
    is_index : bool
        Flag indicating whether the request is for the index page (default is False).

    Returns
    -------
    _TemplateResponse
        Rendered template response containing the processed results or an error message.

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

    try:
        query: IngestionQuery = await parse_query(
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
        # hack to print error message when query is not defined
        if "query" in locals() and query is not None and isinstance(query, dict):
            _print_error(query["url"], exc,max_file_size, pattern_type, pattern)
        else:
            print(f"{Colors.BROWN}WARN{Colors.END}: {Colors.RED}<- {Colors.END}", end="")
            print(f"{Colors.RED}{exc}{Colors.END}")
        
    if len(content) > MAX_DISPLAY_SIZE:
        content = (
            f"(Files content cropped to {int(MAX_DISPLAY_SIZE / 1_000)}k characters,"
            "download full ingest to see more)\n" + content[:MAX_DISPLAY_SIZE]
        )

    _print_success(
        url=query.url,
        max_file_size=max_file_size,
        pattern_type=pattern_type,
        pattern=pattern,
        summary=summary,
    )

    return IngestSuccessResponse(
        repo_url=input_text,
        short_repo_url= short_repo_url,
        summary=summary,
        tree=tree,
        content=content,
        default_max_file_size=max_file_size,
        pattern_type=pattern_type,
        pattern=pattern,
    )


def _print_error(url: str, e: Exception, max_file_size: int, pattern_type: str, pattern: str) -> None:
    """
    Print a formatted summary of the query details, including the URL, file size,
    and pattern information, for easier debugging or logging.

    Parameters
    ----------
    url : str
        The URL associated with the query.
    max_file_size : int
        The maximum file size allowed for the query, in bytes.
    pattern_type : str
        Specifies the type of pattern to use, either "include" or "exclude".
    pattern : str
        The actual pattern string to include or exclude in the query.
    """
    print(f"{Colors.WHITE}{url:<20}{Colors.END}", end="")
    if int(max_file_size / 1024) != 50:
        print(f" | {Colors.YELLOW}Size: {int(max_file_size/1024)}kb{Colors.END}", end="")
    if pattern_type == "include" and pattern != "":
        print(f" | {Colors.YELLOW}Include {pattern}{Colors.END}", end="")
    elif pattern_type == "exclude" and pattern != "":
        print(f" | {Colors.YELLOW}Exclude {pattern}{Colors.END}", end="")


def _print_query(url: str, max_file_size: int, pattern_type: str, pattern: str) -> None:
    """
    Print a formatted summary of the query details, including the URL, file size,
    and pattern information, for easier debugging or logging.

    Parameters
    ----------
    url : str
        The URL associated with the query.
    max_file_size : int
        The maximum file size allowed for the query, in bytes.
    pattern_type : str
        Specifies the type of pattern to use, either "include" or "exclude".
    pattern : str
        The actual pattern string to include or exclude in the query.
    """
    print(f"{Colors.WHITE}{url:<20}{Colors.END}", end="")
    if int(max_file_size / 1024) != 50:
        print(f" | {Colors.YELLOW}Size: {int(max_file_size/1024)}kb{Colors.END}",end="")
    if pattern_type == "include" and pattern != "":
        print(f" | {Colors.YELLOW}Include {pattern}{Colors.END}",end="")
    elif pattern_type == "exclude" and pattern != "":
        print(f" | {Colors.YELLOW}Exclude {pattern}{Colors.END}", end="")




def _print_error(url: str, e: Exception, max_file_size: int, pattern_type: str, pattern: str) -> None:
    """
    Print a formatted error message including the URL, file size, pattern details, and the exception encountered,
    for debugging or logging purposes.

    Parameters
    ----------
    url : str
        The URL associated with the query that caused the error.
    e : Exception
        The exception raised during the query or process.
    max_file_size : int
        The maximum file size allowed for the query, in bytes.
    pattern_type : str
        Specifies the type of pattern to use, either "include" or "exclude".
    pattern : str
        The actual pattern string to include or exclude in the query.
    """
    print(f"{Colors.BROWN}WARN{Colors.END}: {Colors.RED}<- {Colors.END}", end="")
    _print_query(url, max_file_size, pattern_type, pattern)
    print(f" | {Colors.RED}{e}{Colors.END}")

def _print_success(url: str, max_file_size: int, pattern_type: str, pattern: str, summary: str) ->None:
    """
    Print a formatted success message, including the URL, file size, pattern details, and a summary with estimated
    tokens, for debugging or logging purposes.

    Parameters
    ----------
    url : str
        The URL associated with the successful query.
    max_file_size : int
        The maximum file size allowed for the query, in bytes.
    pattern_type : str
        Specifies the type of pattern to use, either "include" or "exclude".
    pattern : str
        The actual pattern string to include or exclude in the query.
    summary : str
        A summary of the query result, including details like estimated tokens.
    """
    estimated_tokens = summary[summary.index("Estimated tokens:") + len("Estimated tokens:") :]
    print(f"{Colors.GREEN}INFO{Colors.END}: {Colors.GREEN}<- {Colors.END}", end="")
    _print_query(url, max_file_size, pattern_type, pattern)
    print(f" | {Colors.PURPLE}{estimated_tokens}{Colors.END}")











    