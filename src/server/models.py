"""查询表单的 Pydantic 模型。"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Union, Optional

from pydantic import BaseModel, Field, field_validator
from server.server_config import MAX_FILE_SIZE_KB

from repoingest.utils.compat_func import removesuffix

if TYPE_CHECKING:
    from server.form_types import IntForm, OptStrForm, StrForm


class PatternType(str, Enum):
    """用于文件过滤的模式类型枚举。"""

    INCLUDE = "include"
    EXCLUDE = "exclude"


class IngestRequest(BaseModel):
    """/api/ingest 端点的请求模型。

    属性
    ----------
    input_text : str
        要摄入的 Git 仓库 URL 或 slug。
    max_file_size : int
        用于过滤文件的最大文件大小滑块位置（0-500）。
    pattern_type : PatternType
        用于文件过滤的模式类型（include 或 exclude）。
    pattern : str
        用于文件过滤的 Glob/正则模式字符串。
    token : str | None
        用于访问私有仓库的 GitHub 个人访问令牌（PAT）。

    """

    input_text: str = Field(..., description="Git repository URL or slug to ingest")
    max_file_size: int = Field(
        ..., ge=1, le=MAX_FILE_SIZE_KB, description="File size in KB"
    )
    pattern_type: PatternType = Field(
        default=PatternType.EXCLUDE, description="Pattern type for file filtering"
    )
    pattern: str = Field(
        default="", description="Glob/regex pattern for file filtering"
    )
    token: str | None = Field(
        default=None, description="GitHub PAT for private repositories"
    )

    @field_validator("input_text")
    @classmethod
    def validate_input_text(cls, v: str) -> str:
        if not v.strip():
            err = "input_text cannot be empty"
            raise ValueError(err)
        return removesuffix(v.strip(), ".git")

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, v: str) -> str:
        """验证 ``pattern`` 字段。"""
        return v.strip()

    @field_validator("max_file_size", mode="before")
    @classmethod
    def str_to_int(cls, v):
        if isinstance(v, str) and v.isdigit():
            return int(v)
        return v

    @field_validator("token", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        if v == "":
            return None
        return v


class IngestSuccessResponse(BaseModel):
    """/api/ingest 端点的成功响应模型。

    属性
    ----------
    repo_url : str
        被处理的原始仓库 URL。
    short_repo_url : str
        仓库 URL 的简短形式（user/repo）。
    summary : str
        摄入过程的摘要，包含 token 估算值。
    digest_url : str
        下载完整摘要内容的 URL（S3 URL 或本地下载端点）。
    tree : str
        仓库的文件树结构。
    content : str
        仓库文件中处理后的内容。
    default_max_file_size : int
        使用的文件大小滑块位置。
    pattern_type : str
        用于过滤的模式类型。
    pattern : str
        用于过滤的模式。

    """

    repo_url: str = Field(..., description="Original repository URL")
    short_repo_url: str = Field(..., description="Short repository URL (user/repo)")
    summary: str = Field(..., description="Ingestion summary with token estimates")
    tree: str = Field(..., description="File tree structure")
    content: str = Field(..., description="Processed file content")
    default_max_file_size: int = Field(
        ..., description="File size slider position used"
    )
    pattern_type: str = Field(..., description="Pattern type used")
    pattern: str = Field(..., description="Pattern used")


class IngestErrorResponse(BaseModel):
    """/api/ingest 端点的错误响应模型。

    属性
    ----------
    error : str
        描述出错原因的错误信息。

    """

    error: str = Field(..., description="Error message")


class JobCreatedResponse(BaseModel):
    """创建摄入任务时立即返回的响应。

    属性
    ----------
    job_id : str
        后台任务的唯一标识符。
    status : str
        创建时始终为 ``running``。

    """

    job_id: str = Field(..., description="Job identifier for polling")
    status: str = Field(
        "running", description="Job status (always running on creation)"
    )


class JobStatusResponse(BaseModel):
    """摄入任务的状态，可选择附带完整结果。

    属性
    ----------
    id : str
        任务标识符。
    status : str
        为 ``running``、``done`` 或 ``error`` 之一。
    result : IngestSuccessResponse | None
        任务成功完成时的摄入结果。
    error : str | None
        任务失败时的错误信息。

    """

    id: str = Field(..., description="Job identifier")
    status: str = Field(..., description="running | done | error")
    result: Optional[IngestSuccessResponse] = Field(
        None, description="Result when done"
    )
    error: Optional[str] = Field(None, description="Error message when failed")


# API 响应的联合类型
IngestResponse = Union[IngestSuccessResponse, IngestErrorResponse]


class QueryForm(BaseModel):
    """查询的表单数据。

    属性
    ----------
    input_text : str
        表单中提供的文本或 URL。
    max_file_size : int
        用户指定的输入允许的最大文件大小。
    pattern_type : str
        查询使用的模式类型（``include`` 或 ``exclude``）。
    pattern : str
        Glob/正则模式字符串。
    token : str | None
        用于访问私有仓库的 GitHub 个人访问令牌（PAT）。

    """

    input_text: str
    max_file_size: int
    pattern_type: str
    pattern: str
    token: str | None = None

    @classmethod
    def as_form(
        cls,
        input_text: StrForm,
        max_file_size: IntForm,
        pattern_type: StrForm,
        pattern: StrForm,
        token: OptStrForm,
    ) -> QueryForm:
        """从 FastAPI 表单参数创建 QueryForm。

        参数
        ----------
        input_text : StrForm
            用户提供的输入文本。
        max_file_size : IntForm
            输入允许的最大文件大小。
        pattern_type : StrForm
            查询使用的模式类型（``include`` 或 ``exclude``）。
        pattern : StrForm
            Glob/正则模式字符串。
        token : OptStrForm
            用于访问私有仓库的 GitHub 个人访问令牌（PAT）。

        返回
        -------
        QueryForm
            QueryForm 实例。

        """
        return cls(
            input_text=input_text,
            max_file_size=max_file_size,
            pattern_type=pattern_type,
            pattern=pattern,
            token=token,
        )
