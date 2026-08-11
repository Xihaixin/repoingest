import os
from pathlib import Path

def removesuffix(s: str, suffix: str) -> str:
    """
    从字符串中移除后缀。

    兼容 Python 3.8。

    参数
    ----------
    s : str
        要移除后缀的字符串。
    suffix : str
        要移除的后缀。

    返回
    -------
    str
        移除后缀后的字符串。

    """
    return s[:len(suffix)] if s.endswith(suffix) else s