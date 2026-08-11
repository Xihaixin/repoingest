"""本模块包含摄取（ingestion）流程的 dataclass。 """
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Set

from pydantic import BaseModel, ConfigDict, Field

from gitingest.config import MAX_FILE_SIZE

@dataclass
class CloneConfig:
    """
    克隆 Git 仓库的配置。

    此类保存将仓库克隆到本地路径所需的参数，包括仓库的 URL、目标本地路径，
    以及指定 commit 或 branch 的可选参数。

    属性
    ----------
    url : str
        要克隆的 Git 仓库的 URL。
    local_path : str
        仓库将被克隆到的本地目录。
    commit : str, optional
        克隆后要检出的特定 commit 哈希（默认值为 None）。
    branch : str, optional
        要克隆的分支（默认值为 None）。
    subpath : str
        要从仓库克隆的子路径（默认值为 "/"）。
    """

    url: str
    local_path: str
    commit: Optional[str] = None
    branch: Optional[str] = None
    subpath: str = "/"
    blob: bool = False

class IngestionQuery(BaseModel):    # pylint: disable=too-many-instance-attributes
    """
    用于存储仓库或文件路径解析后详细信息的 Pydantic 模型。
    """
    user_name: Optional[str] = None
    repo_name: Optional[str] =None
    url: Optional[str] = None
    local_path: Path
    slug: str
    id: str
    subpath: str = "/"
    type: Optional[str] = None
    branch: Optional[str] = None
    commit: Optional[str] = None
    max_file_size: int = Field(default=MAX_FILE_SIZE)
    ignore_patterns: Optional[Set[str]] = None
    include_patterns: Optional[Set[str]] = None 

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def extract_clone_config(self) -> CloneConfig:
        """
        提取 CloneConfig 对象所需的相应字段。

        返回
        -------
        CloneConfig
            一个包含相应字段的 CloneConfig 对象。
        
        异常
        ------
        ValueError
            如果未提供 'url' 参数。
        """
        if not self.url:
            raise ValueError("The 'url' is required.")

        return CloneConfig(
            url=self.url,
            local_path=str(self.local_path),
            commit=self.commit,
            branch=self.branch,
            subpath=self.subpath,
            blob=self.type == "blob",
        )