"""路由层共享的工具函数与依赖。"""

from fastapi import HTTPException, Request

from gitingest.utils.logger import get_logger

logger = get_logger("routers_utils")

UID_COOKIE_NAME = "repoingest_uid"


def require_uid(request: Request) -> str:
    """校验请求携带浏览器身份 cookie ``repoingest_uid``。

    本项目未对外开放 API，API 仅服务于本站前端，而本站前端必然携带该
    cookie。因此把 uid 作为 API 的准入凭证：取不到 uid 的请求（直接调用
    API、爬虫、禁用 cookie）一律拒绝，不进入任何业务处理。

    参数
    ----------
    request : Request
        传入的 HTTP 请求。

    返回
    -------
    str
        当前浏览器的伪身份标识。

    异常
    ------
    HTTPException
        当请求缺少 ``repoingest_uid`` cookie 时抛出 ``400``。
    """
    uid = request.cookies.get(UID_COOKIE_NAME, "")
    if not uid:
        raise HTTPException(status_code=400, detail="missing uid")
    return uid
