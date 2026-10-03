"""服务器的工具函数。"""

import asyncio
import datetime
import math
import platform
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import Response
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from gitingest.config import TMP_BASE_PATH
from gitingest.utils.git_utils import ensure_git_installed
from gitingest.utils.logger import get_logger
from server.job_store import cancel_pending, cleanup_loop
from server.server_config import DELETE_REPO_AFTER

logger = get_logger("server_utils")


def _rate_limit_key(request: Request) -> str:
    """
    返回速率限制的限流键（客户端 IP）。

    默认的 ``slowapi.util.get_remote_address`` 直接使用 ``request.client.host``，
    在反向代理（Nginx）之后该值恒为 ``127.0.0.1``，会导致**所有用户共用一个
    限流桶**——一个用户触发限流，全员被拒。

    这里改为优先取 ``X-Forwarded-For`` 的**最右侧**条目：它由直连的可信反向
    代理追加，客户端无法伪造（伪造的条目只会落在更左侧）。该取值与 uvicorn
    ``--proxy-headers`` 的语义一致。

    参数
    ----------
    request : Request
        传入的 HTTP 请求。

    返回
    -------
    str
        用于限流计数的客户端 IP。
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",")[-1].strip()
        if ip:
            return ip
    return request.client.host if request.client else "unknown"


# 初始化速率限制器
limiter = Limiter(key_func=_rate_limit_key)


async def rate_limit_exception_handler(request: Request, exc: Exception) -> Response:
    """
    用于速率限制错误的自定义异常处理器。

    参数
    ----------
    request : Request
        传入的 HTTP 请求。
    exc : Exception
        引发的异常，预期为 RateLimitExceeded。

    返回
    -------
    Response
        表示已超过速率限制的响应。

    异常
    ------
    exc
        如果异常不是 RateLimitExceeded 错误，则重新抛出。
    """
    if isinstance(exc, RateLimitExceeded):
        logger.warning(
            "Rate limit exceeded for {}",
            request.client.host if request.client else "unknown",
        )
        return _rate_limit_exceeded_handler(request, exc)
    raise exc


@asynccontextmanager
async def lifespan(_: FastAPI):
    """
    处理 FastAPI 应用程序启动和关闭事件的生命周期管理器。

    参数
    ----------
    _ : FastAPI
        FastAPI 应用程序实例（未使用）。

    产生
    -------
    None
        在后台任务运行期间将控制权交还给 FastAPI 应用程序。
    """
    logger.info("Starting server lifecycle: initializing Git check and cleanup tasks")
    task = asyncio.create_task(_remove_old_repositories())
    job_cleanup_task = asyncio.create_task(cleanup_loop())
    yield
    logger.info("Shutting down server lifecycle: cancelling cleanup tasks")
    task.cancel()
    job_cleanup_task.cancel()
    cancel_pending()
    try:
        await task
        await job_cleanup_task
    except asyncio.CancelledError:
        pass


async def _remove_old_repositories():
    """
    定期移除旧的仓库文件夹。

    定期运行以清理旧仓库目录的后台任务。

    该任务：
    - 每 60 秒扫描 TMP_BASE_PATH 目录
    - 移除创建时间早于 DELETE_REPO_AFTER 秒的目录
    - 删除前，如果存在匹配的 .txt 文件，则将仓库 URL 记录到 history.txt
    - 如果删除失败，则优雅地处理错误

    仓库 URL 从每个目录中的第一个 .txt 文件提取，
    假定文件名为 "owner-repository.txt" 格式。
    """
    while True:
        try:
            if not TMP_BASE_PATH.exists():
                await asyncio.sleep(60)
                continue

            current_time = time.time()

            for folder in TMP_BASE_PATH.iterdir():
                if not any(folder.iterdir()):
                    folder.rmdir()
                    logger.debug("Removed empty folder: {}", folder)
                    continue
                folder_stat = folder.stat()
                if platform.system() == "Windows":
                    folder_time = folder_stat.st_ctime
                else:
                    try:
                        folder_time = folder_stat.st_birthtime
                    except AttributeError:
                        folder_time = folder_stat.st_mtime

                if current_time - folder_time <= DELETE_REPO_AFTER:
                    continue

                await _process_folder(folder)

        except Exception as exc:
            logger.exception("Error in _remove_old_repositories: {}", exc)

        await asyncio.sleep(60)


async def _process_folder(folder: Path) -> None:
    """
    处理单个文件夹的删除与日志记录。

    参数
    ----------
    folder : Path
        待处理文件夹的路径。
    """
    # 在删除前尝试记录仓库 URL
    try:
        txt_files = [f for f in folder.iterdir() if f.suffix == ".txt"]

        if txt_files:
            filename = txt_files[0].stem
            if "-" in filename:
                owner, repo = filename.split("-", 1)
                repo_url = f"{owner}/{repo}"

                with open("history.txt", mode="a", encoding="utf-8") as f:
                    current_utc_time = datetime.datetime.now(
                        datetime.timezone.utc
                    ).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    f.write(f"[UTC]{current_utc_time} | {repo_url}\n")

                logger.info(
                    "Logged repository {} to history.txt before deletion", repo_url
                )

    except Exception as exc:
        logger.exception("Error logging repository URL for {}: {}", folder, exc)

    # 删除文件夹
    try:
        shutil.rmtree(folder)
        logger.info("Deleted old repository folder: {}", folder)
    except Exception as exc:
        logger.exception("Error deleting {}: {}", folder, exc)


def log_slider_to_size(position: int) -> int:
    """
    使用对数刻度将滑块位置转换为以字节为单位的文件大小。

    参数
    ----------
    position : int
        范围从 0 到 500 的滑块位置。

    返回
    -------
    int
        与滑块位置对应的以字节为单位的文件大小。
    """
    maxp = 500
    minv = math.log(1)
    maxv = math.log(102_400)
    return round(math.exp(minv + (maxv - minv) * pow(position / maxp, 1.5))) * 1024
