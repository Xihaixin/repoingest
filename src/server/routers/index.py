"""该模块定义用于首页 / 落地页的 FastAPI 路由。"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from server.i18n import LANGUAGES
from server.server_config import EXAMPLE_REPOS, render_template, get_version_info

router = APIRouter()


def _safe_next(next_url: str) -> str:
    """返回一个安全的本地重定向目标（防止开放重定向）。"""
    if next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return "/"


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def home(request: Request) -> HTMLResponse:
    """
    渲染用于向新访客介绍项目的落地页。

    参数
    ----------
    request : Request
        传入的 HTTP 请求。

    返回
    -------
    HTMLResponse
        渲染后的落地页。
    """
    context = {
        "examples": EXAMPLE_REPOS,
    }
    context.update(get_version_info())

    return render_template("home.jinja", request, **context)


@router.get("/app", response_class=HTMLResponse, include_in_schema=False)
async def app_page(request: Request) -> HTMLResponse:
    """
    渲染 Ingest 工具页面（表单 + 结果）。

    参数
    ----------
    request : Request
        传入的 HTTP 请求。

    返回
    -------
    HTMLResponse
        渲染后的工具页面。
    """
    context = {
        "examples": EXAMPLE_REPOS,
        "default_max_file_size": 243,
        "repo_url": request.query_params.get("repo", ""),
    }
    context.update(get_version_info())

    return render_template("index.jinja", request, **context)


@router.get("/lang/{code}", include_in_schema=False)
async def switch_language(request: Request, code: str) -> RedirectResponse:
    """
    将所选语言持久化到 cookie 中，并重定向回调用方。

    参数
    ----------
    request : Request
        传入的 HTTP 请求。
    code : str
        受支持的语言代码之一（例如 ``zh-CN``、``en``）。

    返回
    -------
    RedirectResponse
        重定向回 ``next``（或 ``/``），并设置语言 cookie。
    """
    if code not in LANGUAGES:
        code = "en"

    next_url = _safe_next(request.query_params.get("next", "/"))
    response = RedirectResponse(url=next_url, status_code=302)
    response.set_cookie(
        key="lang",
        value=code,
        path="/",
        httponly=True,
        samesite="lax",
        max_age=365 * 24 * 3600,
    )
    return response
