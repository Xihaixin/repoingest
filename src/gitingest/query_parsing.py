"""本模块包含解析和校验输入来源及模式的函数"""
import hashlib
import re
import uuid
import warnings
from pathlib import Path
from typing import List, Optional, Set, Union
from urllib.parse import unquote, urlparse

from gitingest.config import TMP_BASE_PATH
from gitingest.schemas import IngestionQuery
from gitingest.utils.exceptions import InvalidPatternError
from gitingest.utils.git_utils import check_repo_exists, fetch_remote_branch_list
from gitingest.utils.ignore_patterns import DEFAULT_IGNORE_PATTERNS
from gitingest.utils.query_parser_utils import (
    KNOW_GIT_HOSTS,
    _get_user_and_repo_from_path,
    _is_valid_git_commit_hash,
    _is_valid_pattern,
    _normalize_pattern,
    _validate_host,
    _validate_url_scheme,
)

async def parse_query(
        source: str,
        max_file_size: int,
        from_web: bool,
        include_patterns: Optional[Union[str,Set[str]]] = None,
        ignore_patterns: Optional[Union[str,Set[str]]] = None,
) -> IngestionQuery:
    """
    解析输入来源（URL 或路径）以提取查询相关详情。

    该函数解析输入来源，以提取用户名、仓库名、提交哈希、分支名等信息。它还会处理包含和忽略模式，
    以过滤查询中要包含或排除的文件和目录。

    参数
    ----------
    source : str
        要解析的来源 URL 或文件路径。
    max_file_size : int
        要包含的最大文件大小（字节）。
    from_web : bool
        指示来源是否为网页 URL 的标志。
    include_patterns : Union[str, Set[str]], optional
        要包含的模式，默认值为 None。可以是字符串集合或单个字符串。
    ignore_patterns : Union[str, Set[str]], optional
        要忽略的模式，默认值为 None。可以是字符串集合或单个字符串。

    返回
    -------
    IngestionQuery
        包含仓库或文件路径解析详情的 dataclass 对象。
    """
    # 根据来源类型确定解析方法 
    if from_web or urlparse(source).scheme in ("https", "http") or any(h in source for h in KNOW_GIT_HOSTS):
        # 我们处理的要么是完整 URL，要么是没有域名的 slug
        query = await _parse_remote_repo(source)
    else:
        # 本地路径场景
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

async def _parse_remote_repo(source: str) -> IngestionQuery:
    """
    将仓库 URL 解析为结构化的查询字典。

    如果来源是：
      - 完整的 URL（https://gitlab.com/...），则解析并校验其域名
      - 缺少 'https://' 的 URL（gitlab.com/...），则补上 'https://' 并解析
      - 'slug'（如 'pandas-dev/pandas'），则尝试已知域名直到找到存在的那个。

    参数
    ----------
    source : str
        要解析的 URL 或无域名的 slug。

    返回
    -------
    IngestionQuery
        包含仓库解析详情的字典。
    """
    source = unquote(source)

    # 尝试解析
    parsed_url = urlparse(source)

    if parsed_url.scheme:
        _validate_url_scheme(parsed_url.scheme)
        _validate_host(parsed_url.netloc.lower())

    else: # 形式为 'host/user/repo' 或 'user/repo'
        tmp_host = source.split("/")[0].lower()
        if "." in tmp_host:
            _validate_host(tmp_host)
        else:
            # 无 scheme、无域名 => 用户输入了 "user/repo"，因此我们猜测域名。
            host = await try_domain_for_user_and_repo(*_get_user_and_repo_from_path(source)) 
            source = f"{host}/{source}"

        source = "https://" + source
        parsed_url = urlparse(source)

    host = parsed_url.netloc.lower()
    user_name, repo_name = _get_user_and_repo_from_path(parsed_url.path)
    url = f"https://{host}/{user_name}/{repo_name}"

    # 使用 URL 哈希进行确定性目录命名（支持缓存复用）
    _id = hashlib.md5(url.encode()).hexdigest()[:12]
    slug = f"{user_name}-{repo_name}"
    local_path = TMP_BASE_PATH / _id / slug

    parsed = IngestionQuery(
        user_name=user_name,
        repo_name=repo_name,
        url=url,
        local_path=local_path,
        slug=slug,
        id=_id,
    )

    remaining_parts = parsed_url.path.strip("/").split("/")[2:]

    if not remaining_parts:
        return parsed
    
    possible_type = remaining_parts.pop(0) # 例如 'issues'、'pull'、'tree'、'blob'

    # 如果没有额外的路径部分，直接返回
    if not remaining_parts:
        return parsed
    
    # 如果是 issues 页面或 pull requests，直接返回，不处理子路径
    if remaining_parts and possible_type in ("issues", "pull"):
        return parsed
    
    parsed.type = possible_type

    # 提交或分支
    commit_or_branch = remaining_parts[0]
    if _is_valid_git_commit_hash(commit_or_branch):
        parsed.commit = commit_or_branch
        remaining_parts.pop(0)
    else:
        parsed.branch = await _config_branch_and_subpath(remaining_parts, url)

    # 如果还有剩余路径，则作为子路径
    if remaining_parts:
        parsed.subpath += "/".join(remaining_parts)

    return parsed

async def _config_branch_and_subpath(remaining_parts: List[str], url: str) -> Optional[str]:
    """
    根据 URL 的剩余部分配置分支和子路径。
    参数
    ----------
    remaining_parts : List[str]
        URL 路径的剩余部分。
    url : str
        仓库的 URL。
    返回
    -------
    str, optional
        找到的分支名称，否则为 None。
    """
    try:
        # 从远程仓库获取分支列表
        branches: List[str] = await fetch_remote_branch_list(url)
    except RuntimeError as exc:
        warnings.warn(f"Warning: Failed to fetch branch list: {exc}", RuntimeWarning)
        return remaining_parts.pop(0)
    
    branch = []
    while remaining_parts:
        branch.append(remaining_parts.pop(0))
        branch_name = "/".join(branch)
        if branch_name in branches:
            return branch_name
    
    return None



async def try_domain_for_user_and_repo(user_name: str, repo_name: str) -> str:
    """
        尝试为给定的 user_name 和 repo_name 找到有效的仓库主机。

    参数
    ----------
    user_name : str
        仓库的用户名或所有者。
    repo_name : str
        仓库的名称。

    返回
    -------
    str
        有效仓库主机的域名。

    异常
    ------
    ValueError
        如果没有为给定的 user_name 和 repo_name 找到有效的仓库主机。
    """

    for domain in KNOW_GIT_HOSTS:
        candidate = f"https://{domain}/{user_name}/{repo_name}"
        if await check_repo_exists(candidate):
            return domain
    raise ValueError(f"Could not find a valid repository host for '{user_name}/{repo_name}'.")


def _parse_local_dir_path(path_str: str) ->IngestionQuery:
    """
    将给定的文件路径解析为结构化的查询字典。

    参数
    ----------
    path_str : str
        要解析的文件路径。

    返回
    -------
    IngestionQuery
        包含文件路径解析详情的字典。
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
    解析并校验用于包含或排除的文件/目录模式。

    接受单个模式字符串或模式字符串集合，并将它们处理为规范化列表。
    模式会按逗号和空格拆分，校验允许的字符，然后进行规范化。

    参数
    ----------
    pattern : Set[str] | str
        要解析的模式——可以是单个字符串或字符串集合。

    返回
    -------
    Set[str]
        规范化后的模式集合。

    异常
    ------
    InvalidPatternError
        如果任何模式包含无效字符。仅允许字母数字字符、
        连字符 (-)、下划线 (_)、点 (.)、正斜杠 (/)、加号 (+) 和
        星号 (*)。
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
