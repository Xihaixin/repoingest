"""This module contains functions to parse and validate input sources and patterns"""
import re
import uuid
import warnings
from pathlib import Path
from typing import List, Optional, Set, Union

from gitingest.config import TMP_BASE_PATH
from gitingest.schemas import IngestionQuery
from gitingest.utils.exceptions import InvalidPatternError
from gitingest.utils.ignore_patterns import DEFAULT_IGNORE_PATTERNS
from gitingest.utils.query_parser_utils import (
    _is_valid_pattern,
    _normalize_pattern,
)

async def parse_query(
        source: str,
        max_file_size: int,
        from_web: bool,
        include_patterns: Optional[Union[str,Set[str]]] = None,
        ignore_patterns: Optional[Union[str,Set[str]]] = None,
) -> IngestionQuery:
    """
    Parse the input source (URL or path) to extract relevant details for the query.

    This function parses the input source to extract details such as the username, repository name,
    commit hash, branch name, and other relevant information. It also processes the include and ignore
    patterns to filter the files and directories to include or exclude from the query.

    Parameters
    ----------
    source : str
        The source URL or file path to parse.
    max_file_size : int
        The maximum file size in bytes to include.
    from_web : bool
        Flag indicating whether the source is a web URL.
    include_patterns : Union[str, Set[str]], optional
        Patterns to include, by default None. Can be a set of strings or a single string.
    ignore_patterns : Union[str, Set[str]], optional
        Patterns to ignore, by default None. Can be a set of strings or a single string.

    Returns
    -------
    IngestionQuery
        A dataclass object containing the parsed details of the repository or file path.
    """

    if False:
        pass
    else:
        query = _parse_local_dir_path(source)
    
    ignore_patterns_set = DEFAULT_IGNORE_PATTERNS.copy()
    if ignore_patterns:
        ignore_patterns_set.update(_parse_patterns(ignore_patterns))
    
    if include_patterns:
        parsed_include = _parse_patterns(include_patterns)

        ignore_patterns_set = set(ignore_patterns_set) - set(parsed_include)
    else:
        parsed_include = None

    return IngestionQuery(
        user_name=query.user_name,
        repo_name=query.repo_name,
        url=query.url,
        subpath=query.subpath,
        local_path=query.local_path,
        slug=query.slug,
        id=query.id,
        type = query.type,
        branch=query.branch,
        commit=query.commit,
        max_file_size=max_file_size,
        ignore_patterns=ignore_patterns_set,
        include_patterns=parsed_include,

    )

def _parse_local_dir_path(path_str: str) ->IngestionQuery:
    """
    Parse the given file path into a structured query dictionary.

    Parameters
    ----------
    path_str : str
        The file path to parse.

    Returns
    -------
    IngestionQuery
        A dictionary containing the parsed details of the file path.
    """
    path_obj = Path(path_str).resolve()
    slug = path_obj.name if path_str == "." else path_str.strip("/")
    return IngestionQuery(
        user_name=None,
        repo_name=None,
        url=None,
        local_path=path_obj,
        slug=slug,
        id=str(uuid.uuid4()),
    )

def _parse_patterns(pattern:Union[str,Set[str]]) -> Set[str]:
    """
    Parse and validate file/directory patterns for inclusion or exclusion.

    Takes either a single pattern string or set of pattern strings and processes them into a normalized list.
    Patterns are split on commas and spaces, validated for allowed characters, and normalized.

    Parameters
    ----------
    pattern : Set[str] | str
        Pattern(s) to parse - either a single string or set of strings

    Returns
    -------
    Set[str]
        A set of normalized patterns.

    Raises
    ------
    InvalidPatternError
        If any pattern contains invalid characters. Only alphanumeric characters,
        dash (-), underscore (_), dot (.), forward slash (/), plus (+), and
        asterisk (*) are allowed.
    """

    patterns = pattern if isinstance(pattern,Set) else {pattern}
    parsed_patterns:Set[str] = set()

    for p in patterns:
        parsed_patterns = parsed_patterns.union(set(re.split(","|""),p))

    parsed_patterns = parsed_patterns - {""}
    parsed_patterns = {p.replace("\\","/") for p in parsed_patterns}

    for p in parsed_patterns:
        if not _is_valid_pattern(p):
            raise InvalidPatternError(p)
    
    return {_normalize_pattern(p) for p in parsed_patterns}
