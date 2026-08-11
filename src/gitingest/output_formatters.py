"""摄取并分析代码库目录或单个文件的函数"""
import tiktoken
from typing import Optional, Tuple

from gitingest.query_parsing import IngestionQuery
from gitingest.schemas import FileSystemNode, FileSystemNodeType
from gitingest.utils.logger import get_logger

logger = get_logger("output_formatters")

def format_node(node:FileSystemNode, query: IngestionQuery) -> Tuple[str,str,str]:
    """
    为给定的文件系统节点生成摘要、目录结构和文件内容。

    如果节点表示目录，该函数将递归处理其内容。

    参数
    ----------
    node : FileSystemNode
        要生成摘要的文件系统节点。
    query : IngestionQuery
        包含仓库信息和查询参数的已解析查询对象。

    返回
    -------
    Tuple[str, str, str]
        包含摘要、目录结构和文件内容的元组。
    """
    is_single_file = node.type == FileSystemNodeType.FILE
    summary = _create_summary_prefix(query, single_file=is_single_file)

    if node.type == FileSystemNodeType.DIRECTORY:
        summary += f"Files analyzed:{node.file_count}\n"
    elif node.type == FileSystemNodeType.FILE:
        summary += f"File:{node.name}\n"
        summary += f"Lines:{len(node.content.splitlines()):,}\n"

    tree = "Directory structure:\n" + _create_tree_structure(query, node)
    _create_tree_structure(query, node)

    content = _gather_file_contents(node)

    token_estimate = _format_token_count(tree + content)
    if token_estimate:
        summary += f"\nEstimated tokens:{token_estimate}"

    return summary, tree, content

def _create_summary_prefix(query: IngestionQuery, single_file: bool = False) -> str:
    """
    创建用于汇总仓库或本地目录的前缀字符串。

    包含仓库名称（如果提供）、提交/分支详情，以及相关的子路径。

    参数
    ----------
    query : IngestionQuery
        包含仓库信息和查询参数的已解析查询对象。
    single_file : bool
        指示摘要是否针对单个文件的标志，默认值为 False。

    返回
    -------
    str
        包含仓库、提交、分支和子路径详情的摘要前缀字符串。
    """
    parts = []

    if query.user_name:
        parts.append(f"Repository: {query.user_name}/{query.repo_name}")
    else:
        parts.append(f"Directory: {query.slug}")
    
    if query.commit:
        parts.append(f"Commit: {query.commit}")
    elif query.branch and query.branch not in ("main", "master"):
        parts.append(f"Branch: {query.branch}")

    if query.subpath != "/" and not single_file:
        parts.append(f"Subpath: {query.subpath}")

    return "\n".join(parts) + "\n"

def _create_tree_structure(query: IngestionQuery, node: FileSystemNode, prefix: str = "", is_last: bool = True) -> str:
    """
    生成文件结构的树状字符串表示。

    该函数生成目录结构的字符串表示，格式化为树状，并对嵌套的目录和文件使用适当的缩进。

    参数
    ----------
    query : IngestionQuery
        包含仓库信息和查询参数的已解析查询对象。
    node : FileSystemNode
        当前正在处理的目录或文件节点。
    prefix : str
        用于树状结构缩进和格式化的字符串，默认值为 ""。
    is_last : bool
        指示当前节点是否为其目录中的最后一个节点，默认值为 True。

    返回
    -------
    str
        表示格式化为树状的目录结构的字符串。
    """
    if not node.name:
        node.name = query.slug

    tree_str = ""
    current_prefix = "└── " if is_last else "├──"

    display_name = node.name
    if node.type == FileSystemNodeType.DIRECTORY:
        display_name += "/"
    elif node.type == FileSystemNodeType.SYMLINK:
        display_name += " -> " + node.path.readlink().name

    tree_str += f"{prefix}{current_prefix}{display_name}\n"

    if node.type == FileSystemNodeType.DIRECTORY and node.children:
        prefix += "    " if is_last else "│   "
        for i, child in enumerate(node.children):
            tree_str += _create_tree_structure(query, node=child, prefix=prefix, is_last=i == len(node.children) - 1)
    return tree_str

def _gather_file_contents(node: FileSystemNode) -> str:
    """
    递归收集给定节点下所有文件的内容。

    该函数递归处理目录节点，收集该节点下所有文件的内容。它以单个字符串的形式返回所有文件内容的拼接结果。

    参数
    ----------
    node : FileSystemNode
        当前正在处理的目录或文件节点。

    返回
    -------
    str
        给定节点下所有文件内容的拼接字符串。
    """
    logger.debug("Handling file node: {} (type={})", node.name, node.type)
    if node.type != FileSystemNodeType.DIRECTORY:
        return node.content_string
    logger.debug("Directory children: {}", [child.name for child in node.children])
    return "\n".join(_gather_file_contents(child) for child in node.children)

def _format_token_count(text: str) -> Optional[str]:
    """
    返回表示给定文本 token 数的可读字符串。

    例如：'120' -> '120'，'1200' -> '1.2k'，'1200000' -> '1.2M'。

    参数
    ----------
    text : str
        需要估算 token 数的文本字符串。

    返回
    -------
    str, optional
        格式化后的 token 数字符串（例如 '1.2k'、'1.2M'），如果发生错误则返回 `None`。
    """
    try:
        encoding = tiktoken.get_encoding("cl100k_base")
        total_tokens = len(encoding.encode(text, disallowed_special=()))
    except (ValueError, UnicodeEncodeError) as exc:
        logger.error("Token estimation failed: {}", exc)
        return None
    
    if total_tokens >= 1_000_000:
        return f"{total_tokens / 1_000_000:.1f}M"
    
    if total_tokens >= 1_000:
        return f"{total_tokens / 1_000:.1f}k"
    
    return str(total_tokens)

