"""FastAPI 应用的主模块。"""
import os
import sys
import asyncio
import uvicorn
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from starlette.middleware.trustedhost import TrustedHostMiddleware

# ── 日志必须在任何其他使用它的 import 之前配置 ──
from repoingest.utils.logger import setup_logging, get_logger

# 代码目录（包含 .env、server/、repoingest/）是解析相对日志路径的参考基准，
# 因此日志位置不依赖于进程的工作目录。
_PKG_DIR = Path(__file__).resolve().parent.parent

# 确定一个合理的默认日志文件路径
_log_dir = _PKG_DIR / "logs"
_log_dir.mkdir(parents=True, exist_ok=True)
_default_log_file = str(_log_dir / "repoingest.log")

# 环境变量优先，其次回退到默认路径。
# 相对路径的 REPOINGEST_LOG_FILE 会相对于代码目录解析。
_env_log_file = os.getenv("REPOINGEST_LOG_FILE")
if _env_log_file:
    _log_file = (
        _env_log_file
        if os.path.isabs(_env_log_file)
        else str((_PKG_DIR / _env_log_file).resolve())
    )
else:
    _log_file = _default_log_file

setup_logging(log_file=_log_file)
logger = get_logger("server")

logger.info("Logging to file: {}", _log_file)

# 从 .env 文件加载环境变量
load_dotenv(dotenv_path=_PKG_DIR / ".env")

from server.routers import download, dynamic, index, ingest, jobs
from server.middleware import RequestLoggingMiddleware
from server.server_config import templates
from server.server_utils import lifespan, limiter, rate_limit_exception_handler


if sys.platform == "win32":
    logger.info("Setting ProactorEventLoopPolicy for Uvicorn server on Windows.")
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# 初始化带 lifespan 的 FastAPI 应用
app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter

# 注册用于速率限制的自定义异常处理器
app.add_exception_handler(RateLimitExceeded, rate_limit_exception_handler)


# 动态挂载静态文件目录，以提供 CSS、JS 及其他静态资源
static_dir = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


# 从环境变量获取允许的主机列表，否则使用默认值
allowed_hosts = os.getenv("ALLOWED_HOSTS")
if allowed_hosts:
    allowed_hosts = allowed_hosts.split(",")
else:
    # 定义应用的默认允许主机列表
    default_allowed_hosts = ["repoingest.top", "*.repoingest.top", "localhost", "127.0.0.1"]
    allowed_hosts = default_allowed_hosts

logger.debug("Allowed hosts: {}", allowed_hosts)

# 添加中间件以强制校验允许的主机
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

# 请求追踪：置于最外层中间件，以便为每个请求（即使是被拒绝的请求）
# 分配 request_id 并记录其完整生命周期
app.add_middleware(RequestLoggingMiddleware)


@app.get("/health")
async def health_check() -> Dict[str, str]:
    """健康检查端点。"""
    return {"status": "healthy"}


@app.head("/")
async def head_root() -> HTMLResponse:
    """
    响应根 URL 的 HTTP HEAD 请求。

    镜像首页的响应头与状态码。

    返回
    -------
    HTMLResponse
        带有适当响应头的空 HTML 响应。
    """
    return HTMLResponse(content=None, headers={"content-type": "text/html; charset=utf-8"})


@app.get("/api/", response_class=HTMLResponse)
@app.get("/api", response_class=HTMLResponse)
async def api_docs(request: Request) -> HTMLResponse:
    """
    渲染 API 文档页面。

    参数
    ----------
    request : Request
        传入的 HTTP 请求。

    返回
    -------
    HTMLResponse
        一个渲染后的、展示 API 文档的 HTML 页面。
    """
    return templates.TemplateResponse("api.jinja", {"request": request})


@app.get("/llms.txt")
async def llms() -> FileResponse:
    """
    提供 `llms.txt` 文件供 AI 代理读取。

    返回
    -------
    FileResponse
        位于静态目录中的 `llms.txt` 文件。
    """
    llms_txt_path = static_dir / "llms.txt"
    return FileResponse(str(llms_txt_path))


@app.get("/robots.txt")
async def robots() -> FileResponse:
    """
    提供 `robots.txt` 文件以指导搜索引擎爬虫。

    返回
    -------
    FileResponse
        位于静态目录中的 `robots.txt` 文件。
    """
    robots_txt_path = static_dir / "robots.txt"
    return FileResponse(str(robots_txt_path))


# 注册各模块端点的路由
app.include_router(index)
app.include_router(download)
app.include_router(ingest)
app.include_router(jobs)
app.include_router(dynamic)


if __name__ == "__main__":
    port = int(os.getenv("REPOINGEST_PORT", 8000))
    host = os.getenv("REPOINGEST_HOST", "127.0.0.1")
    logger.info("Starting FastAPI server at http://{}:{}", host, port)

    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        reload=False,
        loop="asyncio",
        access_log=False,
        log_config=None,
    )

    server = uvicorn.Server(config=config)
    server.run()
    