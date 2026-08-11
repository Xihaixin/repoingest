"""该模块定义用于处理动态路径请求的 dynamic 路由。"""

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse

from server.models import IngestRequest, PatternType
from server.routers.ingest import create_ingest_job
from server.server_config import render_template
from server.server_utils import limiter

router = APIRouter()


@router.get("/{full_path:path}")
async def catch_all(request: Request, full_path: str) -> HTMLResponse:
    """
    根据提供的路径渲染包含 Git URL 的页面。

    该端点捕获所有带动态路径的 GET 请求，使用 `full_path` 参数构造一个 Git URL，
    并以该 URL 渲染 `git.jinja` 模板。

    参数
    -------
    request : Request
        传入的请求对象，为渲染响应提供上下文。
    full_path : str
        从 URL 中提取的完整路径，用于构造 Git URL。

    返回
    -------
    HTMLResponse
        一个 HTML 响应，包含渲染后的模板、Git URL 以及其他默认参数
        （如加载状态和文件大小）。
    """
    return render_template(
        "git.jinja",
        request,
        repo_url=full_path,
        loading=True,
        default_file_size=243,
    )


@router.post("/{full_path:path}")
@limiter.limit("10/minute")
async def process_catch_all(
    request: Request,
    input_text: str = Form(...),
    max_file_size: int = Form(...),
    pattern_type: PatternType = Form(...),
    pattern: str = Form(...),
    token: str = Form(""),
) -> JSONResponse:
    """
    处理包含用户查询参数输入的表单提交。

    该端点捕获原生（无 JavaScript）表单提交，并将其转发到与 ``POST /api/ingest``
    相同的后台任务流水线，返回相同的 ``202`` 响应并带有 ``job_id``。

    参数
    -------
    request : Request
        传入的请求对象，为渲染响应提供上下文。
    input_text : str
        用户提交的用于处理的输入文本，默认取自表单。
    max_file_size : int
        用户指定的输入最大允许文件大小。
    pattern_type : PatternType
        用户指定的查询所用模式类型。
    pattern : str
        用户指定的查询所用的模式字符串。
    token : str
        用于私有仓库的可选 GitHub 个人访问令牌。

    返回
    -------
    JSONResponse
        一个 ``202`` 响应，内容为 ``{"job_id": ..., "status": "running"}``，
        与 ``/api/ingest`` 端点返回一致。
    """
    ingest_request = IngestRequest(
        input_text=input_text,
        max_file_size=max_file_size,
        pattern_type=pattern_type,
        pattern=pattern,
        token=token,
    )
    payload = await create_ingest_job(request, ingest_request)
    return JSONResponse(status_code=202, content=payload)
