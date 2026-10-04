"""PostHog 分析客户端封装。

后端在服务启动时初始化 PostHog 客户端，在后台摄取任务的关键节点上报事件。
所有分析调用都做了失败隔离：PostHog 不可用时不得影响主业务。

身份约定：``distinct_id`` 复用浏览器 cookie ``repoingest_uid``，与前端
（``static/js/analytics.js`` 的 ``bootstrap.distinctID``）保持一致，从而把
页面行为与后端任务结果归入同一身份链。
"""

from __future__ import annotations

from typing import Any, Optional

from posthog import Posthog

from repoingest.utils.logger import get_logger
from server.server_config import POSTHOG_API_KEY, POSTHOG_ENABLED, POSTHOG_HOST

logger = get_logger("analytics")

_client: Optional[Posthog] = None


def init() -> None:
    """初始化 PostHog 客户端（未启用或缺少 key 时为空操作）。"""
    global _client

    if not (POSTHOG_ENABLED and POSTHOG_API_KEY):
        logger.info("PostHog analytics disabled")
        return

    try:
        _client = Posthog(POSTHOG_API_KEY, host=POSTHOG_HOST)
        logger.info("PostHog analytics enabled | host={}", POSTHOG_HOST)
    except Exception:
        _client = None
        logger.exception("Failed to initialize PostHog")


def shutdown() -> None:
    """刷新队列并关闭客户端，避免进程退出时丢失事件。"""
    global _client

    if _client is None:
        return

    try:
        _client.shutdown()
    except Exception:
        logger.exception("Failed to shut down PostHog")
    finally:
        _client = None


def capture(
    distinct_id: str, event: str, properties: Optional[dict[str, Any]] = None
) -> None:
    """上报一个事件（失败时静默，绝不抛出）。"""
    if _client is None or not distinct_id:
        return

    try:
        _client.capture(event, distinct_id=distinct_id, properties=properties or {})
    except Exception:
        logger.debug("PostHog capture failed for event {}", event, exc_info=True)
