"""服务器的配置。"""

import os
from pathlib import Path
from typing import Any, Dict, List

from fastapi import Request
from fastapi.templating import Jinja2Templates

from server.i18n import i18n_context

MAX_DISPLAY_SIZE: int = 300_000
DEFAULT_FILE_SIZE_KB: int = 5 * 1024  # 5 MB
DELETE_REPO_AFTER: int = 5 * 24 * 60 * 60  # 5 天，以秒为单位
MAX_FILE_SIZE_KB: int = 100 * 1024  # 100 MB

EXAMPLE_REPOS: List[Dict[str, str]] = [
    {"name": "Repoingest", "url": "https://gitee.com/xihaishen/repoingest"},
    {"name": "FastAPI", "url": "https://github.com/tiangolo/fastapi"},
    {"name": "Flask", "url": "https://github.com/pallets/flask"},
    {"name": "Excalidraw", "url": "https://github.com/excalidraw/excalidraw"},
    {"name": "ApiAnalytics", "url": "https://github.com/tom-draper/api-analytics"},
]

# 版本与仓库配置
APP_REPOSITORY = os.getenv(
    "APP_REPOSITORY", "https://gitee.com/xihaishen/repoingest"
)
APP_VERSION = os.getenv("APP_VERSION", "0.1.0")
APP_VERSION_URL = os.getenv(
    "APP_VERSION_URL", "https://gitee.com/xihaishen/repoingest"
)


def get_version_info() -> dict:
    """获取版本信息，包括展示版本和链接。

    返回
    -------
    dict[str, str]
        包含 'version' 和 'version_link' 键的字典。

    """
    # 使用来自 GitHub Actions 的预计算值
    display_version = APP_VERSION
    version_link = APP_VERSION_URL

    # 如果未提供 URL，则回退到仓库根目录
    if version_link == APP_REPOSITORY or not version_link:
        version_link = f"{APP_REPOSITORY.rstrip('/')}/tree/main"

    return {
        "version": display_version,
        "version_link": version_link,
    }


templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


def render_template(name: str, request: Request, **context: Any):
    """使用共享的 i18n 上下文渲染模板。

    向每个页面注入 ``request``、``lang``、``t``（翻译可调用对象）和
    ``messages``（前端使用），这样模板就可以调用
    ``{{ t('some.key') }}``。
    """
    ctx = i18n_context(request)
    ctx.update(context)
    return templates.TemplateResponse(name, ctx)
