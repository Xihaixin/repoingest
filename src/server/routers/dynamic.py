"""该模块定义用于处理动态路径请求的 dynamic 路由。"""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from gitingest.utils.logger import get_logger
from gitingest.utils.query_parser_utils import is_valid_repo_url_path
from server.models import IngestRequest, PatternType
from server.routers.ingest import create_ingest_job
from server.routers_utils import require_uid
from server.server_config import render_template
from server.server_utils import limiter

logger = get_logger("dynamic")

router = APIRouter()

# 全捕获路由不需要被搜索引擎与扫描器当作"任意路径都可访问"，
# 故对渲染次数单独限流，避免被批量探测刷量。
CATCH_ALL_RATE_LIMIT = "30/minute"


def _reject_invalid_repo_path(full_path: str) -> None:
    """
    校验 ``/{full_path:path}`` 捕获到的路径是否具备 ``owner/repo`` 形状。

    参数
    ----------
    full_path : str
        从 URL 中提取的完整路径。

    异常
    ------
    HTTPException
        当路径不符合仓库地址语法时抛出 ``404``。
    """
    if not is_valid_repo_url_path(full_path):
        logger.info("Rejected non-repo path: {}", full_path)
        raise HTTPException(status_code=404, detail="Not Found")


@router.get("/{full_path:path}")
@limiter.limit(CATCH_ALL_RATE_LIMIT)
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

    异常
    ------
    HTTPException
        当路径不符合仓库地址语法时抛出 ``404``。
    """
    _reject_invalid_repo_path(full_path)
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
    full_path: str,
    input_text: str = Form(...),
    max_file_size: int = Form(...),
    pattern_type: PatternType = Form(...),
    pattern: str = Form(...),
    token: str = Form(""),
    uid: str = Depends(require_uid),
) -> JSONResponse:
    """
    处理包含用户查询参数输入的表单提交。

    该端点捕获原生（无 JavaScript）表单提交，并将其转发到与 ``POST /api/ingest``
    相同的后台任务流水线，返回相同的 ``202`` 响应并带有 ``job_id``。

    参数
    -------
    request : Request
        传入的请求对象，为渲染响应提供上下文。
    full_path : str
        从 URL 中提取的完整路径；仅用于仓库地址语法校验，
        实际处理的来源取自表单的 ``input_text``。
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

    异常
    ------
    HTTPException
        当路径不符合仓库地址语法时抛出 ``404``。
    """
    _reject_invalid_repo_path(full_path)
    ingest_request = IngestRequest(
        input_text=input_text,
        max_file_size=max_file_size,
        pattern_type=pattern_type,
        pattern=pattern,
        token=token,
    )
    payload = await create_ingest_job(uid, ingest_request)
    return JSONResponse(status_code=202, content=payload)
