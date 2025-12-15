import asyncio
import aiohttp
from typing import List, Tuple

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

async def run_command(*args: str) -> Tuple[bytes, bytes]:
    """
    Execute a shell command asynchronously and return (stdout, stderr) bytes.

    Parameters
    ----------
    *args : str
        The command and its arguments to execute.

    Returns
    -------
    Tuple[bytes, bytes]
        A tuple containing the stdout and stderr of the command.

    Raises
    ------
    RuntimeError
        If command exits with a non-zero status.
    """
    # Execute the requested command
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        error_message = stderr.decode().strip()
        raise RuntimeError(f"Command failed:{' '.join(args)}\nError: {error_message}")

    return stdout, stderr

async def ensure_git_installed() ->None:
    """
    Ensure Git is installed and accessible on the system.

    Raises
    ------
    RuntimeError
        If Git is not installed or not accessible.
    """
    try:
        await run_command("git", "--version")
        print('git exist in the environment.')
    except RuntimeError as exc:
        print(f"ERROR DETAILS: {exc}")
        msg = "Git is not installed or not accessible. Please install Git first."
        raise RuntimeError(msg) from exc

async def fetch_remote_branch_list(url: str) -> List[str]:
    """
    Fetch the list of branches from a remote Git repository.
    Parameters
    ----------
    url : str
        The URL of the Git repository to fetch branches from.
    Returns
    -------
    List[str]
        A list of branch names available in the remote repository.
    """
    fetch_branches_command = ["git", "ls-remote", "--heads", url]
    await ensure_git_installed()
    stdout, _ = await run_command(*fetch_branches_command)
    stdout_decoded = stdout.decode()

    return [
        line.split("refs/heads/", 1)[1]
        for line in stdout_decoded.splitlines()
        if line.strip() and "refs/heads/" in line
    ]