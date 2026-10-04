"""摄取（ingestion）流程的实用函数。"""

from fnmatch import fnmatch
from pathlib import Path
from typing import Set

def _should_exclude(path: Path, base_path: Path,ignore_patterns: Set[str]) -> bool:
    """
    判断给定的文件或目录路径是否与任何忽略模式匹配。

    此函数检查文件或目录的相对路径是否与任何指定的忽略模式匹配。如果匹配，
    则返回 `True`，表示应从后续处理中排除该文件或目录。

    参数
    ----------
    path : Path
        要检查的文件或目录的绝对路径。
    base_path : Path
        计算相对路径所依据的基目录。
    ignore_patterns : Set[str]
        用于与相对路径进行匹配的模式集合。

    返回
    -------
    bool
        如果路径与任一忽略模式匹配则返回 `True`，否则返回 `False`。
    """
    try:
        rel_path = path.relative_to(base_path)
    except ValueError:
        return True
    
    rel_str = str(rel_path)
    for pattern in ignore_patterns:
        if pattern and fnmatch(rel_str, pattern):
            return True
    return False

def _should_include(path: Path, base_path: Path, include_patterns: Set[str]) ->bool:
    """
    判断给定的文件或目录路径是否与任何包含模式匹配。

    此函数检查文件或目录的相对路径是否与任何指定模式匹配。如果找到匹配，
    则返回 `True`，表示该文件或目录应包含在后续处理中。

    参数
    ----------
    path : Path
        要检查的文件或目录的绝对路径。
    base_path : Path
        计算相对路径所依据的基目录。
    include_patterns : Set[str]
        用于与相对路径进行匹配的模式集合。

    返回
    -------
    bool
        如果路径与任一包含模式匹配则返回 `True`，否则返回 `False`。
    """
    try:
        rel_path = path.relative_to(base_path)
    except ValueError:
        return False
    
    rel_str = str(rel_path)
    if path.is_dir():
        rel_str += "/"
    
    for pattern in include_patterns:
        if fnmatch(rel_str, pattern):
            return True
    return False