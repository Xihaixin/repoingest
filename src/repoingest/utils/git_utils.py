import asyncio
import os
import time
import aiohttp
from typing import List

import git
from git import GitCommandError, RemoteProgress

from repoingest.utils.logger import get_logger

logger = get_logger("git_utils")

# 默认请求头，用于模拟合法的 Git 客户端
_GIT_HTTP_HEADERS: dict[str, str] = {
    "User-Agent": "git/2.43.0",
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate",
}

# 仓库存在性探测的超时时间（秒）。较短的超时时间可以防止预检请求卡住：
# 一旦超时，调用方会直接回退到克隆操作，从而快速得到真实结果。
_DEFAULT_PROBE_TIMEOUT = 10


def _probe_timeout() -> float:
    """返回仓库探测超时时间（秒），可通过环境变量配置。"""
    raw = os.getenv("REPOINGEST_PROBE_TIMEOUT", "")
    try:
        return float(raw) if raw else _DEFAULT_PROBE_TIMEOUT
    except ValueError:
        return _DEFAULT_PROBE_TIMEOUT


class CloneProgress(RemoteProgress):
    """Git 克隆操作的进度回调。"""

    def update(self, op_code, cur_count, max_count=None, message=""):
        pass  # 静默进度


async def check_repo_exists(url: str) -> bool:
    """
    检查远程 Git 仓库是否存在，且可通过 HTTP(S) 访问。

    该函数探测的是 **Git 智能协议端点**（``info/refs``），而非 Web UI
    首页，这样可以对 Git 托管平台（GitHub、GitLab、Bitbucket、Gitee 等）
    给出可靠的判断结果。

    参数
    ----------
    url : str
        Git 仓库 URL，例如 ``https://github.com/user/repo``。

    返回
    -------
    bool
        仓库存在且可访问时返回 ``True``；
        仓库确实不存在或为私有仓库时返回 ``False``。

    异常
    ------
    RuntimeError
        当遇到意外的 HTTP 状态码（如 500、403），
        或发生网络错误导致无法完成检查时抛出。
    """
    # ── 1. 规范化 URL ────────────────────────────────────────────────
    # Git 托管平台要求智能协议端点带有 ".git" 后缀；如果缺失则补上。
    url = url.rstrip("/")
    if not url.endswith(".git"):
        url += ".git"

    # 智能协议端点
    probe_url = f"{url}/info/refs?service=git-upload-pack"

    logger.info(
        "Probing repository existence via Git smart protocol: {}",
        probe_url,
    )

    # 较短且可配置的超时时间：一旦超时，调用方无论如何都会回退到克隆操作，
    # 因此过长的探测只会徒增无谓的延迟。
    probe_timeout = _probe_timeout()
    timeout = aiohttp.ClientTimeout(total=probe_timeout)
    start_time = time.monotonic()

    try:
        async with aiohttp.ClientSession(
            timeout=timeout, headers=_GIT_HTTP_HEADERS
        ) as session:
            async with session.get(probe_url, allow_redirects=True) as response:
                elapsed = time.monotonic() - start_time
                status = response.status
                content_type = response.headers.get("Content-Type", "N/A")
                content_length = response.headers.get("Content-Length", "N/A")

                logger.debug(
                    "Repository probe responded [status={}, type={}, length={}, elapsed={:.2f}s]",
                    status,
                    content_type,
                    content_length,
                    elapsed,
                )

                # ── 2. 状态码解释 ─────────────────────────────────
                # 200 OK – 智能协议端点已返回 refs
                if status == 200:
                    logger.info(
                        "Repository EXISTS [{}] (200, {:.2f}s)", url, elapsed
                    )
                    return True

                # 301 Moved Permanently – 永久重定向（客户端会自动跟随）
                if status == 301:
                    location = response.headers.get("Location", "unknown")
                    logger.warning(
                        "Repository URL returned 301 → {}, trying follow", location
                    )
                    # `allow_redirects=True` 已自动跟随重定向；如果最终仍
                    # 停留在 301，说明重定向链异常结束——按存在处理
                    return True

                # 302 Found – GitLab 常用于将私有仓库重定向到登录页
                if status == 302:
                    logger.info(
                        "Repository returned 302 (likely private or requires auth) [{}]", url
                    )
                    # 无法判断仓库是"存在但私有"还是"根本不存在"。
                    # 交由调用方处理——让真正的 `git clone` 去判断。
                    return True

                # 401 / 403 – 需要认证或访问被拒绝
                if status in (401, 403):
                    logger.warning(
                        "Repository access denied [{}] (HTTP {}) – may be private", url, status
                    )
                    return True  # 可能存在，但受保护

                # 404 Not Found – 仓库确实不存在
                if status == 404:
                    logger.warning(
                        "Repository NOT FOUND [{}] (404, {:.2f}s)", url, elapsed
                    )
                    return False

                # 429 Too Many Requests – 请求过于频繁，触发限流
                if status == 429:
                    retry_after = response.headers.get("Retry-After", "?")
                    logger.error(
                        "Rate limited while probing [{}] (429, retry-after={})",
                        url,
                        retry_after,
                    )
                    raise RuntimeError(
                        f"Rate limited by Git host (HTTP 429). "
                        f"Retry after {retry_after}s."
                    )

                # 5xx – 服务器错误，不能可靠地判定为"不存在"
                if 500 <= status < 600:
                    logger.error(
                        "Git host server error [{}] (HTTP {}, {:.2f}s)",
                        url,
                        status,
                        elapsed,
                    )
                    raise RuntimeError(
                        f"Git host returned server error (HTTP {status}) "
                        f"for {url}"
                    )

                # 其他意外状态码
                logger.error(
                    "Unexpected HTTP status {} probing [{}] ({:.2f}s)",
                    status,
                    url,
                    elapsed,
                )
                raise RuntimeError(
                    f"Unexpected HTTP status {status} when probing {url}"
                )

    except asyncio.TimeoutError:
        elapsed = time.monotonic() - start_time
        logger.warning(
            "Timeout probing repository [{}] ({:.2f}s, timeout={}s)",
            url,
            elapsed,
            probe_timeout,
        )
        raise RuntimeError(
            f"Timeout while checking repository (network may be slow): {url}"
        )

    except aiohttp.ClientConnectorError as exc:
        elapsed = time.monotonic() - start_time
        logger.error(
            "Connection failed probing [{}] ({:.2f}s): {}",
            url,
            elapsed,
            exc,
        )
        raise RuntimeError(
            f"Cannot connect to Git host when checking {url}: {exc}"
        ) from exc

    except aiohttp.ClientError as exc:
        elapsed = time.monotonic() - start_time
        logger.error(
            "HTTP client error probing [{}] ({:.2f}s): {}",
            url,
            elapsed,
            exc,
        )
        raise RuntimeError(
            f"HTTP error while checking repository {url}: {exc}"
        ) from exc


async def ensure_git_installed() -> None:
    """
    确保 Git 已安装且在系统上可访问。
    此函数使用 GitPython 验证 git 可执行文件是否可用。

    异常
    ------
    RuntimeError
        如果 Git 未安装或不可访问。
    """
    try:
        # 在 executor 中运行，避免阻塞事件循环
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _check_git)
        logger.debug("Git is available in the environment.")
    except Exception as exc:
        logger.exception("Git check failed: {}", exc)
        msg = "Git is not installed or not accessible. Please install Git first."
        raise RuntimeError(msg) from exc


def _check_git() -> None:
    """同步检查 git 是否可通过 GitPython 使用。"""
    try:
        git.Git().version()
    except GitCommandError as exc:
        raise RuntimeError(str(exc)) from exc


async def fetch_remote_branch_list(url: str) -> List[str]:
    """
    使用 GitPython 从远程 Git 仓库获取分支列表。

    参数
    ----------
    url : str
        要从中获取分支的 Git 仓库 URL。

    返回
    -------
    List[str]
        远程仓库中可用分支名称的列表。

    异常
    ------
    RuntimeError
        如果 Git 未安装或无法查询远程仓库。
    """
    logger.info("Fetching remote branch list for {}", url)
    await ensure_git_installed()

    start_time = time.monotonic()
    loop = asyncio.get_event_loop()
    branches = await loop.run_in_executor(None, _fetch_branches, url)
    elapsed = time.monotonic() - start_time

    logger.info(
        "Fetched {} branches from {} in {:.2f}s",
        len(branches),
        url,
        elapsed,
    )
    logger.debug("Branches: {}", branches)
    return branches


def _fetch_branches(url: str) -> List[str]:
    """使用 GitPython 获取远程分支列表的同步辅助函数。"""
    try:
        g = git.Git()
        output = g.ls_remote("--heads", url)
        logger.debug("Raw ls-remote output for {}: {} bytes", url, len(output))
        branches = []
        for line in output.splitlines():
            if line.strip() and "refs/heads/" in line:
                branch_name = line.split("refs/heads/", 1)[1]
                branches.append(branch_name)
        logger.debug("Parsed {} branches from ls-remote output", len(branches))
        return branches
    except GitCommandError as exc:
        logger.exception(
            "Git ls-remote failed for {}: {}", url, exc
        )
        raise RuntimeError(f"Failed to fetch branch list for {url}: {exc}") from exc
