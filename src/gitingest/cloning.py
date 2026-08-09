"""This module contains functions for cloning a Git repository to a local path."""
import asyncio
import os
import re
import time
from pathlib import Path
from typing import Optional, Final

from git import Repo, GitCommandError

from gitingest.schemas import CloneConfig
from gitingest.utils.git_utils import check_repo_exists, ensure_git_installed, CloneProgress
from gitingest.utils.logger import get_logger
from gitingest.utils.timeout_wrapper import async_timeout

logger = get_logger("cloning")

TIMEOUT: int = 300  # 5 minutes timeout for larger repos

_GITHUB_PAT_PATTERN: Final[str] = r"^(?:gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9]{22}_[A-Za-z0-9]{59})$"


@async_timeout(TIMEOUT)
async def clone_repo(config: CloneConfig) -> None:
    """
    Clone a repository to a local path based on the provided configuration.

    This function handles the process of cloning a Git repository to the local file system.
    It can clone a specific branch or commit if provided, and it raises exceptions if
    any errors occur during the cloning process.

    Parameters
    ----------
    config : CloneConfig
        The configuration for cloning the repository.

    Raises
    ------
    ValueError
        If the repository is not found or if the provided URL is invalid.
    OSError
        If an error occurs while creating the parent directory for the repository.
    """

    # Extract and validate query parameters
    url: str = config.url
    local_path: str = config.local_path
    commit: Optional[str] = config.commit
    branch: Optional[str] = config.branch
    partial_clone: bool = config.subpath != "/"

    # Create parent directory if it doesn't exist
    parent_dir = Path(local_path).parent

    try:
        os.makedirs(parent_dir, exist_ok=True)
    except OSError as exc:
        logger.error("Failed to create parent directory {}: {}", parent_dir, exc)
        raise OSError(f"Failed to create parent directory {parent_dir}: {exc}") from exc

    # Check if the repository exists
    try:
        repo_exists = await check_repo_exists(url)
        if not repo_exists:
            logger.error("Repository not found: {}", url)
            raise ValueError(
                f"Repository '{url}' not found. Make sure the URL is correct and the repository is public."
            )
    except RuntimeError as exc:
        logger.error(
            "Repository existence check failed for {} (will attempt clone anyway): {}",
            url,
            exc,
        )
        # ── Network-level failures should not block the clone attempt ──
        # The actual `git clone` may succeed where the HTTP probe failed
        # (e.g. different network path, authentication, etc.)

    await ensure_git_installed()

    # Use GitPython to clone the repository in a thread executor
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
    await loop.run_in_executor(None, _clone_repo_sync, config)
    clone_elapsed = time.monotonic() - clone_start
    logger.info("Clone completed in {:.2f}s for {}", clone_elapsed, url)


def _clone_repo_sync(config: CloneConfig) -> None:
    """
    Synchronous helper to clone a repository using GitPython.
    If the target directory already exists, skip cloning (cache reuse).
    
    Parameters
    ----------
    config : CloneConfig
        The clone configuration.
    """
    url = config.url
    local_path = config.local_path
    commit = config.commit
    branch = config.branch
    partial_clone = config.subpath != "/"
    subpath = config.subpath

    # Cache reuse: if directory already exists, skip cloning
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
            # Remove depth for sparse checkout compatibility
            clone_kwargs.pop("depth", None)
            # Clone the repository
            repo = Repo.clone_from(url, local_path, **clone_kwargs)
            
            # Configure sparse checkout
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
        # GitCommandError carries stderr – this is the actual error from Git
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
    Validate the format of a GitHub Personal Access Token.

    Parameters
    ----------
    token : str
        GitHub personal access token (PAT) for accessing private repositories.

    Raises
    ------
    InvalidGitHubTokenError
        If the token format is invalid.

    """
    if not re.fullmatch(_GITHUB_PAT_PATTERN, token):
        logger.warning("Invalid GitHub token format provided")
        raise ValueError("Invalid GitHub token format")
