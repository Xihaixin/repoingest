import os
from pathlib import Path

def removesuffix(s: str, suffix: str) -> str:
    """
    Remove a suffix from a string.

    Compatible with Python 3.8.

    Parameters
    ----------
    s : str
        String to remove suffix from.
    suffix : str
        Suffix to remove.

    Returns
    -------
    str
        String with suffix removed.

    """
    return s[:len(suffix)] if s.endswith(suffix) else s