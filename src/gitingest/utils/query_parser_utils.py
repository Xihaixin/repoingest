import os
import string
from typing import List, Set, Tuple

HEX_DIGITS: Set[str] = set(string.hexdigits)

KNOW_GIT_HOSTS: List[str] = [
    "github.com",
    "gitlab.com",
    "bitbucket.org",
    "gitea.com",
    "codeberg.org",
    "gist.github.com",
    "gitee.com"
]

def _is_valid_pattern(pattern: str) -> bool:
    """
    校验给定的模式字符串是否只包含合法字符。

    此函数检查模式字符串是否仅由字母数字字符或下列允许的字符组成：
    短横线（`-`）、下划线（`_`）、点（`.`）、正斜杠（`/`）、加号（`+`）、
    星号（`*`）或 at 符号（`@`）。

    参数
    ----------
    pattern : str
        要校验的模式字符串。

    返回
    -------
    bool
        如果模式有效则返回 True，否则返回 False。
    """
    return all(c.isalnum() or c in "-_./+*@" for c in pattern)


def _normalize_pattern(pattern:str) -> str:
    """
    通过去除前导分隔符并追加通配符来规范化给定的模式字符串。

    此函数会去掉模式字符串开头的目录分隔符，如果模式以分隔符结尾，
    则追加一个通配符（`*`）。

    参数
    ----------
    pattern : str
        要规范化的模式字符串。

    返回
    -------
    str
        规范化后的模式字符串。
    """
    pattern = pattern.lstrip(os.sep)
    if pattern.endswith(os.sep):
        pattern += "*"
    return pattern

def _validate_url_scheme(scheme: str) -> None:
    """
    校验给定的 scheme 是否属于已知的 scheme。

    参数
    ----------
    scheme: str
        要校验的 scheme。

    异常
    ------
    ValueError
        如果 scheme 不是 "https" 或 "http"。
    """

    if scheme not in ("https", "http"):
        raise ValueError(f"Invalid URL scheme '{scheme}' in URL")

def _validate_host(host: str) -> None:
    """
    校验给定的主机名是否属于已知的 Git 托管平台。

    参数
    ----------
    host: str
        要校验的主机名。

    异常
    ------
        如果主机名不是已知的 Git 托管平台。
    """
    if host not in KNOW_GIT_HOSTS:
        raise ValueError(f"Unknown domain '{host}' in URL")
    

def _get_user_and_repo_from_path(path: str) -> Tuple[str, str]:
    """
    从给定的路径中提取用户名和仓库名。

    参数
    ----------
    path : str
        用于提取用户名和仓库名的路径。

    返回
    -------
    Tuple[str, str]
        包含用户名和仓库名的元组。

    异常
    ------
    ValueError
        如果路径不包含至少两部分。
    """
    path_parts = path.lower().strip("/").split("/")
    if len(path_parts) < 2:
        raise ValueError(f"Invalid repository URL '{path}'")
    return path_parts[0], path_parts[1]

def _is_valid_git_commit_hash(commit: str) -> bool:
    """
    校验给定的字符串是否为合法的 Git 提交哈希值。

    此函数检查提交哈希是否为仅由十六进制数字组成的 40 位字符串，
    这是 Git 提交哈希的标准格式。

    参数
    ----------
    commit : str
        要作为 Git 提交哈希校验的字符串。

    返回
    -------
    bool
        如果字符串是合法的 40 位 Git 提交哈希则返回 True，否则返回 False。
    """
    return len(commit) == 40 and all(c in HEX_DIGITS for c in commit)

