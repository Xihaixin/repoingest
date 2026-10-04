"""定义文件系统表示的架构（schema）。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path

from repoingest.config import SEPARATOR
from repoingest.utils.file_utils import get_preferred_encodings, is_text_file
from repoingest.utils.notebook_utils import process_notebook

class FileSystemNodeType(Enum):
    """表示文件系统节点类型（目录或文件）的枚举。"""
    DIRECTORY = auto()
    FILE = auto()
    SYMLINK = auto()

@dataclass
class FileSystemStats:
    """用于在文件系统遍历期间跟踪统计信息的类。"""

    visited: set[Path] = field(default_factory=set)
    total_files: int = 0
    total_size: int = 0


@dataclass
class FileSystemNode:
    """
    表示文件系统中的一个节点（文件或目录）的类。

    跟踪文件/目录的属性，以便进行全面分析。
    """

    name: str
    type: FileSystemNodeType
    path_str: str
    path: Path
    size:int = 0
    file_count: int = 0
    dir_count: int = 0
    depth: int = 0
    children: list[FileSystemNode] = field(default_factory=list)

    def sort_children(self) -> None:
        """
        按特定顺序对目录的子节点进行排序。

        排序顺序：
          1. 普通文件（不以点开头）
          2. 隐藏文件（以点开头）
          3. 普通目录（不以点开头）
          4. 隐藏目录（以点开头）

        每个分组内部均按字母数字顺序排序。

        异常
        ------
        ValueError
            如果该节点不是目录。
        """
        if self.type != FileSystemNodeType.DIRECTORY:
            raise ValueError("Cannot sort children of a non-directory node")
        
        def _sort_key(child: FileSystemNode) -> tuple[int, str]:
            # 返回优先级
            name = child.name.lower()
            if child.type ==FileSystemNodeType.FILE:
                if name == "readme.md":
                    return (0, name)
                return (1 if not name.startswith(".") else 2, name)
            return (3 if not name.startswith(".") else 4, name)
        
        self.children.sort(key=_sort_key)

    @property
    def content_string(self) -> str:
        """
        以字符串形式返回节点的内容，包括路径和内容。

        返回
        -------
        str
            节点内容的字符串表示。
        """
        parts = [
            SEPARATOR,
            f"{self.type.name}: {str(self.path_str).replace(os.sep, '/')}"
            + (f" -> {self.path.readlink().name}" if self.type == FileSystemNodeType.SYMLINK else ""),
            SEPARATOR,
            F"{self.content}",
        ]
        return "\n".join(parts) + "\n\n"
    
    @property
    def content(self) -> str:
        """
        如果文件是文本（或 notebook），则读取其内容；否则返回错误消息。

        返回
        -------
        str
            文件的内容；如果无法读取文件，则返回错误消息。
        
        异常
        ------
        ValueError
            如果该节点是目录。
        """
        if self.type == FileSystemNodeType.DIRECTORY:
            raise ValueError("Cannot read content of a directory node")
        
        if self.type == FileSystemNodeType.SYMLINK:
            return ""
        
        if not is_text_file(self.path):
            return "[None-text file]"
        
        if self.path.suffix == ".ipynb":
            try:
                return process_notebook(self.path)
            except Exception as exc:
                return f"Error processing notebook: {exc}"
            
        for encoding in get_preferred_encodings():
            try:
                with self.path.open(encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
            except UnicodeError:
                continue
            except OSError as exc:
                return f"Error reading file: {exc}"
        return "Error: Unable to decode file with available encodings."