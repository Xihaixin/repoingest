"""应用的中枢日志配置。

本模块基于 Loguru 提供统一的日志配置。它取代了之前基于标准库
``logging`` 的配置，并增加了以下功能：

* 每一行都包含完整的时间戳（``YYYY-MM-DD HH:mm:ss.SSS``），控制台输出同样如此。
* 每日轮转的文件日志，支持保留策略与压缩。
* 上下文绑定辅助函数（``request_id``、``client_ip`` 等），用于请求追踪。
* 一个桥接器，将标准库 ``logging`` 的日志记录（uvicorn、aiohttp、
  gitpython 等）路由到相同的 Loguru 管道。

用法
-----
    from gitingest.utils.logger import get_logger

    logger = get_logger("ingestion")
    logger.info("Processing started")
    logger.warning("File size limit reached: {}", path)
    logger.error("Failed to process file: {}", exc)
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional

from loguru import logger as _base_logger

# ── 环境变量默认值 ──
_DEFAULT_LOG_LEVEL = "INFO"
_DEFAULT_ROTATION = "00:00"
_DEFAULT_RETENTION = "14 days"
_DEFAULT_COMPRESSION = "gz"

# 可选的附加字段，存在时渲染到人类可读的日志输出中
# （由请求中间件通过 ``logger.contextualize(...)`` 绑定）。
_CONTEXT_LABELS = (
    ("request_id", "rid"),
    ("client_ip", "ip"),
    ("method", "method"),
    ("path", "path"),
)


def _make_formatter(colorize: bool):
    """为人类可读的文本输出构建一个 Loguru 格式化回调。

    时间戳始终包含完整日期（``YYYY-MM-DD HH:mm:ss.SSS``）。
    请求上下文字段仅在绑定时才渲染（例如在处理请求的日志中间件内部），
    从而保持后台/CLI 日志的整洁。
    """

    def _format(record: dict) -> str:
        time_s = record["time"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        level_s = f"{record['level'].name: <8}"
        module_s = record["extra"].get("module", record["name"])

        if colorize:
            parts = [f"<green>{time_s}</green> | <level>{level_s}</level> | {module_s}"]
        else:
            parts = [f"{time_s} | {level_s} | {module_s}"]

        for key, label in _CONTEXT_LABELS:
            value = record["extra"].get(key)
            if value:
                parts.append(f"{label}={value}")

        if colorize:
            parts.append("<level>{message}</level>")
        else:
            parts.append("{message}")

        # 只有当存在 `{exception}` 时，Loguru 才会渲染 traceback。
        if record["exception"] is not None:
            parts.append("{exception}")

        return " | ".join(parts) + "\n"

    return _format


def _env(name: str, default: str) -> str:
    """读取环境变量，当未设置或为空时返回 ``default``。"""
    value = os.getenv(name)
    return value if value else default


class _InterceptHandler(logging.Handler):
    """将标准库 ``logging`` 的日志记录路由到 Loguru 管道。

    将该处理器附加到标准库根 logger 上，使第三方库（uvicorn、aiohttp、
    gitpython 等）与应用日志共享相同的控制台/文件输出端、格式和轮转策略。
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = _base_logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame is not None and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        _base_logger.opt(depth=depth, exception=record.exc_info).log(
            level,
            record.getMessage(),
            module=f"stdlib.{record.name}",
        )


def _setup_stdlib_bridge() -> None:
    """将标准库 ``logging`` 根 logger 重定向到 Loguru。

    uvicorn 的访问日志（access logger）被禁用，因为请求日志中间件已经
    以更丰富的上下文（请求 id、客户端 ip、耗时）记录了每个请求。
    """
    handler = _InterceptHandler()
    logging.basicConfig(handlers=[handler], level=0, force=True)
    logging.getLogger("uvicorn.access").disabled = True


# ── 模块级哨兵变量，确保配置只执行一次 ──
_initialized: bool = False


def setup_logging(
    name: str = "repoingest",
    log_level: Optional[str] = None,
    log_file: Optional[str] = None,
) -> None:
    """配置 Loguru 日志器：彩色控制台输出 + 轮转文件输出端。

    在应用启动时调用一次。后续调用不产生任何效果（保留已有的输出端），
    且永远不会重复添加处理器。

    参数
    ----------
    name : str
        根 logger 命名空间。为保持 API 兼容而保留；通过
        :func:`get_logger` 返回的每个 logger 都以它作为命名空间前缀。
    log_level : str, optional
        取值为 ``DEBUG``、``INFO``、``WARNING``、``ERROR``、``CRITICAL`` 之一。
        回退到 ``REPOINGEST_LOG_LEVEL`` 环境变量，最终回退到 ``INFO``。
    log_file : str, optional
        日志文件路径。回退到 ``REPOINGEST_LOG_FILE`` 环境变量。
        设置后，日志会同时写入控制台和轮转文件。
    """
    global _initialized  # noqa: PLW0603

    if _initialized:
        return

    level = (log_level or _env("REPOINGEST_LOG_LEVEL", _DEFAULT_LOG_LEVEL)).upper()

    # 移除 Loguru 的默认处理器，避免控制台输出重复
    _base_logger.remove()

    # ── 控制台输出端（连接到真实终端时启用彩色输出） ──
    if _env("REPOINGEST_LOG_TO_STDOUT", "1") == "1":
        _base_logger.add(
            sys.stderr,
            level=level,
            format=_make_formatter(colorize=sys.stderr.isatty()),
            colorize=sys.stderr.isatty(),
            backtrace=True,
            diagnose=False,
        )

    # ── 轮转文件输出端 ──
    file_path = log_file or _env("REPOINGEST_LOG_FILE", "")
    if file_path:
        serialize = _env("REPOINGEST_LOG_JSON", "0") == "1"
        _base_logger.add(
            file_path,
            level="DEBUG",
            format=_make_formatter(colorize=False),
            rotation=_env("REPOINGEST_LOG_ROTATION", _DEFAULT_ROTATION),
            retention=_env("REPOINGEST_LOG_RETENTION", _DEFAULT_RETENTION),
            compression=_env("REPOINGEST_LOG_COMPRESSION", _DEFAULT_COMPRESSION),
            encoding="utf-8",
            enqueue=True,
            backtrace=True,
            diagnose=False,
            serialize=serialize,
        )

    _setup_stdlib_bridge()

    _initialized = True


def get_logger(child_name: str):
    """返回绑定到 ``repoingest.<child_name>`` 命名空间的 Loguru 日志器。

    参数
    ----------
    child_name : str
        日志器的子命名空间（例如 ``"server"``、``"cloning"``）。

    返回
    -------
    loguru.Logger
        日志记录会带有指定模块标签的 Loguru 日志器。
    """
    return _base_logger.bind(module=f"repoingest.{child_name}")
