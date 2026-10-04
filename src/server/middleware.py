"""用于请求级追踪的请求日志中间件。

每个 HTTP 请求都会被分配一个唯一的 ``request_id``，并绑定到 Loguru 上下文
中，贯穿整个请求生命周期（路由、解析、克隆、摄取、响应）。这样可以在所有
日志行中端到端地追踪单个失败请求，同时该标识符会通过 ``X-Request-ID``
响应头回传给客户端，便于上报排查。

高流量、低价值的资源请求（例如 ``/static/*``）会直接放行，不生成请求 id
或访问日志条目，以免污染日志。
"""

from __future__ import annotations

import os
import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from repoingest.utils.logger import get_logger

logger = get_logger("server.middleware")

# 比该时长（毫秒）更慢的请求会以 WARNING 级别的日志行上报。
_DEFAULT_SLOW_REQUEST_MS = 30_000

# 高流量、低价值的资源请求路径前缀：不会为它们生成请求 id，
# 也不会输出访问日志行。
_QUIET_PREFIXES = ("/static/",)


def _slow_request_ms() -> float:
    """返回慢请求阈值（毫秒，可通过环境变量配置）。"""
    raw = os.getenv("REPOINGEST_SLOW_REQUEST_MS", "")
    try:
        return float(raw) if raw else _DEFAULT_SLOW_REQUEST_MS
    except ValueError:
        return _DEFAULT_SLOW_REQUEST_MS


def _should_trace(path: str) -> bool:
    """返回请求路径是否需要进行请求 id 追踪与访问日志记录。"""
    return not path.startswith(_QUIET_PREFIXES)


def _client_ip(request: Request) -> str:
    """返回尽最大努力获取的客户端 IP，并处理代理背后的 ``X-Forwarded-For``。"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """为每个请求分配 ``request_id`` 并记录其生命周期。

    请求标识符与客户端元数据会绑定到 Loguru 上下文中，因此处理该请求期间
    输出的每一行日志都会携带这些信息，从而实现单个请求的端到端追踪。
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # 静态资源：直接放行，不生成请求 id 或访问日志条目。
        if not _should_trace(request.url.path):
            logger.debug("Static asset request: {}", request.url.path)
            return await call_next(request)

        request_id = uuid.uuid4().hex[:12]
        client_ip = _client_ip(request)

        with logger.contextualize(
            request_id=request_id,
            client_ip=client_ip,
            method=request.method,
            path=request.url.path,
        ):
            logger.debug("Request started")
            start = time.perf_counter()
            try:
                response = await call_next(request)
            except Exception:
                logger.exception("Unhandled exception while handling request")
                raise

            duration_ms = (time.perf_counter() - start) * 1000
            if duration_ms >= _slow_request_ms():
                logger.warning(
                    "Slow request completed | status={} | duration={:.1f}ms | threshold={:.0f}ms",
                    response.status_code,
                    duration_ms,
                    _slow_request_ms(),
                )
            logger.info(
                "Request completed | status={} | duration={:.1f}ms",
                response.status_code,
                duration_ms,
            )
            response.headers["X-Request-ID"] = request_id
            return response
