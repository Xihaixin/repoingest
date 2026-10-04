"""本模块包含将 Git 仓库克隆到本地路径的函数。"""
import asyncio
import contextvars
import os
import re
import time
from pathlib import Path
from typing import Optional, Final

from git import Repo, GitCommandError

from repoingest.schemas import CloneConfig
from repoingest.utils.git_utils import check_repo_exists, ensure_git_installed, CloneProgress
from repoingest.utils.logger import get_logger
from repoingest.utils.timeout_wrapper import async_timeout

logger = get_logger("cloning")

TIMEOUT: int = 300  # 较大仓库的超时时间为 5 分钟

_GITHUB_PAT_PATTERN: Final[str] = r"^(?:gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9]{22}_[A-Za-z0-9]{59})$"


@async_timeout(TIMEOUT)
async def clone_repo(config: CloneConfig) -> None:
    """
    根据提供的配置将仓库克隆到本地路径。

    该函数负责将 Git 仓库克隆到本地文件系统。如果提供了具体分支或提交，则克隆对应的分支或提交；
    若克隆过程中发生任何错误，则会抛出异常。

    参数
    ----------
    config : CloneConfig
        克隆仓库的配置。

    异常
    ------
    ValueError
        如果仓库不存在，或提供的 URL 无效。
    OSError
        如果创建仓库父目录时发生错误。
    """

    # 提取并校验查询参数
    url: str = config.url
    local_path: str = config.local_path
    commit: Optional[str] = config.commit
    branch: Optional[str] = config.branch
    partial_clone: bool = config.subpath != "/"

    # 如果父目录不存在则创建
    parent_dir = Path(local_path).parent

    try:
        os.makedirs(parent_dir, exist_ok=True)
    except OSError as exc:
        logger.error("Failed to create parent directory {}: {}", parent_dir, exc)
        raise OSError(f"Failed to create parent directory {parent_dir}: {exc}") from exc

    # 检查仓库是否存在
    try:
        repo_exists = await check_repo_exists(url)
        if not repo_exists:
            logger.error("Repository not found: {}", url)
            raise ValueError(
                f"Repository '{url}' not found. Make sure the URL is correct and the repository is public."
            )
    except RuntimeError as exc:
        logger.warning(
            "Repository existence check failed for {} (will attempt clone anyway): {}",
            url,
            exc,
        )
        # ── 网络层故障不应阻塞克隆尝试 ──
        # 实际的 `git clone` 可能会在 HTTP 探测失败的情况下成功
        # （例如不同的网络路径、认证方式等）

    await ensure_git_installed()

    # 使用 GitPython 在线程执行器中克隆仓库
    logger.info(
        "Starting clone for {} [branch={}, commit={}, partial={}, depth={}]",
        url,
        branch or "default",
        commit or "HEAD",
        partial_clone,
        1 if not commit else "full",
    )
    clone_start = time.monotonic()
    loop = asyncio.get_event_loop()
    # 将当前上下文（包括通过 contextualize 绑定到 Loguru 的 request_id）
    # 传播到执行器线程，以便 _clone_repo_sync 内部输出的日志保留请求跟踪 ID。
    ctx = contextvars.copy_context()
    await loop.run_in_executor(None, lambda: ctx.run(_clone_repo_sync, config))
    clone_elapsed = time.monotonic() - clone_start
    logger.info("Clone completed in {:.2f}s for {}", clone_elapsed, url)


def _clone_repo_sync(config: CloneConfig) -> None:
    """
    使用 GitPython 克隆仓库的同步辅助函数。
    如果目标目录已存在，则跳过克隆（缓存复用）。
    
    参数
    ----------
    config : CloneConfig
        克隆配置。
    """
    url = config.url
    local_path = config.local_path
    commit = config.commit
    branch = config.branch
    partial_clone = config.subpath != "/"
    subpath = config.subpath

    # 缓存复用：如果目录已存在，跳过克隆
    if os.path.exists(local_path):
        logger.info("Repository cache found at {}, skipping clone", local_path)
        return

    try:
        clone_kwargs = {
            "single_branch": True,
            "progress": CloneProgress(),
        }

        if not commit:
            clone_kwargs["depth"] = 1
            if branch and branch.lower() not in ("main", "master"):
                clone_kwargs["branch"] = branch

        if partial_clone:
            # 为稀疏检出兼容性移除 depth
            clone_kwargs.pop("depth", None)
            # 克隆仓库
            repo = Repo.clone_from(url, local_path, **clone_kwargs)
            
            # 配置稀疏检出
            sparse_path = subpath.lstrip("/")
            if config.blob:
                sparse_path = str(Path(sparse_path).parent.as_posix())

            repo.git.sparse_checkout("set", sparse_path)
            logger.info("Sparse checkout configured for subpath: {}", sparse_path)
        else:
            repo = Repo.clone_from(url, local_path, **clone_kwargs)

        if commit:
            repo.git.checkout(commit)
            logger.info("Checked out commit: {}", commit)

        logger.info("Repository cloned successfully to {}", local_path)

    except GitCommandError as exc:
        # GitCommandError 携带 stderr —— 这是 Git 返回的实际错误
        git_status = getattr(exc, "status", "?")
        git_stderr = (getattr(exc, "stderr", None) or "").strip()
        git_cmd = " ".join(getattr(exc, "command", ["git", "?"]))

        logger.error(
            "Git operation FAILED for {} (exit code {})\n"
            "  command: {}\n"
            "  stderr: {}",
            url,
            git_status,
            git_cmd,
            git_stderr or "(empty — check system Git configuration)",
        )
        raise RuntimeError(
            f"Git operation failed (exit code {git_status}): {git_stderr or str(exc)}"
        ) from exc


def validate_github_token(token: str) -> None:
    """
    校验 GitHub 个人访问令牌的格式。

    参数
    ----------
    token : str
        用于访问私有仓库的 GitHub 个人访问令牌（PAT）。

    异常
    ------
    InvalidGitHubTokenError
        如果令牌格式无效。

    """
    if not re.fullmatch(_GITHUB_PAT_PATTERN, token):
        logger.warning("Invalid GitHub token format provided")
        raise ValueError("Invalid GitHub token format")
