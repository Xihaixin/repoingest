import asyncio
import os
import time
import aiohttp
from typing import List

import git
from git import GitCommandError, RemoteProgress

from gitingest.utils.logger import get_logger

logger = get_logger("git_utils")

# Default headers to mimic a legitimate Git client
_GIT_HTTP_HEADERS: dict[str, str] = {
    "User-Agent": "git/2.43.0",
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate",
}

# Timeout (seconds) for the repository existence probe.  A short timeout keeps
# the pre-flight check from stalling the request: when it expires the caller
# simply falls back to cloning, which reports the real outcome quickly.
_DEFAULT_PROBE_TIMEOUT = 10


def _probe_timeout() -> float:
    """Return the repository probe timeout in seconds (env-configurable)."""
    raw = os.getenv("REPOINGEST_PROBE_TIMEOUT", "")
    try:
        return float(raw) if raw else _DEFAULT_PROBE_TIMEOUT
    except ValueError:
        return _DEFAULT_PROBE_TIMEOUT


class CloneProgress(RemoteProgress):
    """Progress callback for git clone operations."""

    def update(self, op_code, cur_count, max_count=None, message=""):
        pass  # Silent progress


async def check_repo_exists(url: str) -> bool:
    """
    Check whether a remote Git repository exists and is accessible via HTTP(S).

    This function probes the **Git smart‑protocol endpoint** (``info/refs``)
    rather than the web‑UI landing page, which gives a reliable answer for
    Git‑hosting platforms (GitHub, GitLab, Bitbucket, Gitee, …).

    Parameters
    ----------
    url : str
        Git repository URL, e.g. ``https://github.com/user/repo``.

    Returns
    -------
    bool
        ``True`` if the repository exists and is reachable;
        ``False`` if the repository definitely does not exist or is private.

    Raises
    ------
    RuntimeError
        When an unexpected HTTP status (e.g. 500, 403) is encountered,
        or when a network error prevents the check from completing.
    """
    # ── 1. Normalise the URL ──────────────────────────────────────────
    # Git hosting platforms expect the ".git" suffix for the smart-
    # protocol endpoint; add it if missing.
    url = url.rstrip("/")
    if not url.endswith(".git"):
        url += ".git"

    # Smart‑protocol endpoint
    probe_url = f"{url}/info/refs?service=git-upload-pack"

    logger.info(
        "Probing repository existence via Git smart protocol: {}",
        probe_url,
    )

    # Short, configurable timeout: when it expires the caller falls back to
    # cloning anyway, so a long probe only adds pointless latency.
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

                # ── 2. Status‑code interpretation ──────────────────
                # 200 OK – the smart‑protocol endpoint returned refs
                if status == 200:
                    logger.info(
                        "Repository EXISTS [{}] (200, {:.2f}s)", url, elapsed
                    )
                    return True

                # 301 Moved Permanently – follow redirect (client follows)
                if status == 301:
                    location = response.headers.get("Location", "unknown")
                    logger.warning(
                        "Repository URL returned 301 → {}, trying follow", location
                    )
                    # `allow_redirects=True` already followed it; if we
                    # ended on 301 the chain ended oddly – treat as exists
                    return True

                # 302 Found – often used by GitLab to redirect to sign‑in
                # for private repos.
                if status == 302:
                    logger.info(
                        "Repository returned 302 (likely private or requires auth) [{}]", url
                    )
                    # We can't tell if it *exists* but is private, or
                    # doesn't exist.  Defer to the caller – let the
                    # actual `git clone` decide.
                    return True

                # 401 / 403 – authentication required or access denied
                if status in (401, 403):
                    logger.warning(
                        "Repository access denied [{}] (HTTP {}) – may be private", url, status
                    )
                    return True  # Might exist but is protected

                # 404 Not Found – the repo definitely does not exist
                if status == 404:
                    logger.warning(
                        "Repository NOT FOUND [{}] (404, {:.2f}s)", url, elapsed
                    )
                    return False

                # 429 Too Many Requests – rate‑limited
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

                # 5xx – server error, not a reliable "does not exist"
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

                # Any other unexpected status
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
    Ensure Git is installed and accessible on the system.
    This uses GitPython to verify that the git executable is available.

    Raises
    ------
    RuntimeError
        If Git is not installed or not accessible.
    """
    try:
        # Run in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _check_git)
        logger.debug("Git is available in the environment.")
    except Exception as exc:
        logger.exception("Git check failed: {}", exc)
        msg = "Git is not installed or not accessible. Please install Git first."
        raise RuntimeError(msg) from exc


def _check_git() -> None:
    """Synchronous check that git is available via GitPython."""
    try:
        git.Git().version()
    except GitCommandError as exc:
        raise RuntimeError(str(exc)) from exc


async def fetch_remote_branch_list(url: str) -> List[str]:
    """
    Fetch the list of branches from a remote Git repository using GitPython.

    Parameters
    ----------
    url : str
        The URL of the Git repository to fetch branches from.

    Returns
    -------
    List[str]
        A list of branch names available in the remote repository.

    Raises
    ------
    RuntimeError
        If Git is not installed or the remote cannot be queried.
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
    """Synchronous helper to fetch remote branch list using GitPython."""
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
