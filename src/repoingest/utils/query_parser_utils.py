import os
import re
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

# ──────────────────────────────────────────────────────────────────────
# 仓库路径语法（白名单）
# ──────────────────────────────────────────────────────────────────────
# Web 端把 URL 路径直接当作仓库地址（``/{full_path:path}`` 全捕获路由），
# 因此必须能判定"这条路径是否可能是仓库地址"。
#
# 判定依据不是"它像不像已知的漏洞探测路径"（那样的黑名单永远补不完），
# 而是"它是否满足 :func:`gitingest.query_parsing._parse_remote_repo` 所能
# 消费的语法"，即与解析器完全同源的**白名单**：
#
#     <repo-path> ::= [ <host> "/" ] <owner> "/" <repo> [ "/" <tail> ]
#
#   * ``host``  —— 仅当首段含 "." 时出现；此时解析器会走
#                  :func:`_validate_host` 分支，故必须是已知 Git 主机。
#   * ``owner`` —— 命名空间 / 用户名。
#   * ``repo``  —— 仓库名（可带 ".git" 后缀）。
#   * ``tail``  —— 可选的 "tree/blob/issues/pull/..." 及其子路径，
#                  解析器原样透传，故不对其内容作限制。
#
# 由于 :func:`_get_user_and_repo_from_path` 要求路径至少两段，单段路径
# （``/.env``、``/nginx_status``）与点开头的命名空间（``/.git/config``、
# ``/.aws/credentials``）都不在该语法内，无需单独列出即可被拒绝。

# owner / repo 名称段：以字母数字开头，以字母数字或下划线结尾，
# 中间允许 . _ + -。因此 "."、"-" 开头或 "-" 结尾的段一律不成立。
_NAME_SEGMENT_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._+-]*[A-Za-z0-9_])?")

# Git 仓库名不会是网页文档或服务端脚本。这是白名单中唯一的否定式规则，
# 依据是"仓库名的构成规律"而非"扫描器会打什么"，用于拦下
# ``/druid/index.html`` 这类恰好凑足两段的探测。
_NON_REPO_SUFFIXES: Tuple[str, ...] = (
    ".html", ".htm", ".php", ".asp", ".aspx", ".jsp",
)

_MAX_SEGMENT_LENGTH = 100
_MAX_SEGMENTS = 20
_MAX_PATH_LENGTH = 512


def is_valid_repo_url_path(path: str) -> bool:
    """
    判断给定的 URL 路径是否可能为仓库地址（``owner/repo`` 形式）。

    采用白名单：只接受 :func:`gitingest.query_parsing._parse_remote_repo`
    能够消费的路径形状，其余一律拒绝。它**不**依赖任何已知的漏洞探测路径
    清单，因此对未知、未见过的扫描器同样有效。

    接受
    ----
    ``torvalds/linux``、``vuejs/core``、``torvalds/linux/tree/master``、
    ``github.com/torvalds/linux``、``gitlab.com/group/sub/project``

    拒绝
    ----
    ``.env``、``.git/config``、``.aws/credentials``、``nginx_status``、
    ``phpinfo.php``、``backup/``、``wp-config.php.bak``、``druid/index.html``

    参数
    ----------
    path : str
        不含前导斜杠的 URL 路径（即 ``/{full_path:path}`` 捕获到的值）。

    返回
    -------
    bool
        路径符合仓库地址语法时返回 ``True``，否则返回 ``False``。
    """
    if not path or len(path) > _MAX_PATH_LENGTH:
        return False

    # 容忍单个结尾斜杠（github.com/owner/repo/ 是常见写法），
    # 但路径内部的空段（//）不予接受。
    if path.endswith("/"):
        path = path[:-1]
    if not path or "//" in path:
        return False

    segments = path.strip("/").split("/")
    if not 2 <= len(segments) <= _MAX_SEGMENTS:
        return False

    # 首段带 "." => 解析器会走 _validate_host 分支，故必须是已知 Git 主机；
    # 命中后跳过该段，其后的两段才是 owner / repo。
    if segments[0].lower() in KNOW_GIT_HOSTS:
        segments = segments[1:]
        if len(segments) < 2:
            return False
    elif "." in segments[0]:
        # 带点但不是已知主机：解析器会直接抛 "Unknown domain"。
        return False

    owner, repo = segments[0], segments[1]

    if len(owner) > _MAX_SEGMENT_LENGTH or len(repo) > _MAX_SEGMENT_LENGTH:
        return False
    if not (_NAME_SEGMENT_RE.fullmatch(owner) and _NAME_SEGMENT_RE.fullmatch(repo)):
        return False

    repo_lower = repo.lower()
    return not repo_lower.endswith(_NON_REPO_SUFFIXES)

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

