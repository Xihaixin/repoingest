"""Gitingest 包的工具函数。"""
import asyncio
import functools
from typing import Any, Awaitable, Callable, TypeVar

from repoingest.utils.exceptions import AsyncTimeoutError

T = TypeVar("T")

def async_timeout(seconds) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """
    异步超时装饰器。

    该装饰器包装一个异步函数，并确保其运行时间不超过指定的秒数。
    如果函数执行超出该限制，则抛出 `AsyncTimeoutError`。

    参数
    ----------
    seconds : int
        异步函数允许的最大执行时间（秒）。

    返回
    -------
    Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]
        一个装饰器，应用于异步函数后可确保其在指定的时限内完成。
        如果函数执行时间过长，则抛出 `AsyncTimeoutError`。
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
            except asyncio.TimeoutError as exc:
                raise AsyncTimeoutError(f"Operation timed out after {seconds} seconds") from exc
            
        return wrapper
        
    return decorator
