import asyncio
import aiohttp
from typing import List, Tuple

import git
from git import GitCommandError, RemoteProgress


class CloneProgress(RemoteProgress):
    """Progress callback for git clone operations."""
    def update(self, op_code, cur_count, max_count=None, message=''):
        pass  # Silent progress


async def check_repo_exists(url: str) -> bool:
    """
     Use aiohttp to check Git repository weather exist
    
    Parameters:
    -----------
    url : str
        git repository url
        
    Returns:
    --------
    bool
        True: repository exist, False: doesn't exist or Network is unavailable
    """
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.head(url, allow_redirects=True) as response:
                status = response.status

                if status in (200, 301):
                    return True  
                elif status in (302, 404):
                    return False 
                else:
                    # other status, you can extend it
                    raise RuntimeError(f"Unexpected HTTP status: {status}")
                    
    except aiohttp.ClientError:
        return False
    except asyncio.TimeoutError:
        return False


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
        print('git exist in the environment.')
    except Exception as exc:
        print(f"ERROR DETAILS: {exc}")
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
    """
    await ensure_git_installed()
    
    loop = asyncio.get_event_loop()
    branches = await loop.run_in_executor(None, _fetch_branches, url)
    return branches


def _fetch_branches(url: str) -> List[str]:
    """Synchronous helper to fetch remote branch list using GitPython."""
    try:
        # Use git ls-remote via GitPython to list remote heads
        g = git.Git()
        output = g.ls_remote("--heads", url)
        branches = []
        for line in output.splitlines():
            if line.strip() and "refs/heads/" in line:
                branch_name = line.split("refs/heads/", 1)[1]
                branches.append(branch_name)
        return branches
    except GitCommandError as exc:
        raise RuntimeError(f"Failed to fetch branch list: {exc}") from exc
