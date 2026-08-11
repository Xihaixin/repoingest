"""该模块包含用于下载摘要（digest）文件的 FastAPI 路由。"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from gitingest.config import TMP_BASE_PATH

router = APIRouter()

@router.get("/download/{digest_id}")
async def download_ingest(digest_id: str) -> Response:
    """
    下载与给定摘要 ID 关联的 .txt 文件。

    该函数在对应给定摘要 ID 的目录中查找 `.txt` 文件。如果找到文件，
    则读取其内容并作为可下载附件返回。如果找不到 `.txt` 文件，则抛出异常。

    参数
    ----------
    digest_id : str
        摘要的唯一标识符，用于查找对应的目录并定位其中的 .txt 文件。

    返回
    -------
    Response
        包含所找到 `.txt` 文件内容的 FastAPI Response 对象。该文件以适当的
        媒体类型（`text/plain`）和正确的 `Content-Disposition` 响应头发送，
        以触发文件下载。

    异常
    ------
    HTTPException
        当摘要目录不存在或目录中不存在 `.txt` 文件时抛出。
    """
    directory = TMP_BASE_PATH / digest_id

    try:
        if not directory.exists():
            raise FileNotFoundError("Directory not found")
        
        txt_files = [f for f in directory.iterdir() if f.suffix == ".txt"]
        if not txt_files:
            raise FileNotFoundError("No .txt file found")
        
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Digest not found") from exc
    
    # 在目录中查找第一个 .txt 文件
    first_file = txt_files[0]

    with first_file.open(encoding="utf-8") as f:
        content = f.read()

    return Response(
        content=content,
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename={first_file.name}"},
    )