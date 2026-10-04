"""摄取并分析代码库目录或单个文件的函数。"""
import warnings
from pathlib import Path
from typing import Tuple

from repoingest.config import MAX_DIRECTORY_DEPTH, MAX_FILES, MAX_TOTAL_SIZE_BYTES
from repoingest.output_formatters import format_node
from repoingest.query_parsing import IngestionQuery
from repoingest.schemas import FileSystemNode, FileSystemNodeType, FileSystemStats
from repoingest.utils.ingestion_utils import _should_exclude, _should_include
from repoingest.utils.logger import get_logger

try:
    import tomllib  # type: ignore[import]
except ImportError:
    import tomli as tomllib

logger = get_logger("ingestion")

def ingest_query(query: IngestionQuery) -> Tuple[str,str,str]:
    """
    为已解析的查询运行摄取流程。

    这是分析代码库目录或单个文件的主入口函数。它处理查询参数，读取文件或目录内容，并生成摘要、
    目录结构和文件内容，以及 token 估算。

    参数
    ----------
    query : IngestionQuery
        包含仓库信息和查询参数的已解析查询对象。

    返回
    -------
    Tuple[str, str, str]
        包含摘要、目录结构和文件内容的元组。

    异常
    ------
    ValueError
        如果路径不存在、不是文件，或文件没有内容。
    """
    
    subpath = Path(query.subpath.strip('/')).as_posix()
    path = query.local_path / subpath

    apply_gitingest_file(path, query)

    if not path.exists():
        raise ValueError(f"{query.slug} cannot be found")

    if (query.type and query.type == "blob") or query.local_path.is_file():
        # TODO 我们这样做是错的！我们仍然应该检查分支和提交！
        if not path.is_file():
            raise ValueError(f"Path {path} is not a file")
        relative_path = path.relative_to(query.local_path)

        file_node = FileSystemNode(
            name=path.name,
            type=FileSystemNodeType.FILE,
            size=path.stat().st_size,
            file_count=1,
            path_str=str(relative_path),
            path=path,
        )

        if not file_node.content:
            raise ValueError(f"File {file_node.name} has no content")
        
        return format_node(file_node, query)

    root_node = FileSystemNode(
        name=path.name,
        type=FileSystemNodeType.DIRECTORY,
        path_str=str(path.relative_to(query.local_path)),
        path=path,
    )

    stats = FileSystemStats()

    _process_node(
        node=root_node,
        query=query,
        stats=stats,
    )

    return format_node(root_node, query)

def apply_gitingest_file(path: Path, query: IngestionQuery) -> None:
    """
    将 .gitingest 文件应用到查询对象上。

    该函数读取指定路径下的 .gitingest 文件，并使用文件中找到的忽略模式更新查询对象。

    参数
    ----------
    path : Path
        要摄取的目录路径。
    query : IngestionQuery
        包含仓库信息和查询参数的已解析查询对象。
        它应具有 `ignore_patterns` 属性，该属性为 None 或字符串集合。
    """

    path_gitingest = path / ".gitingest"

    if not path_gitingest.is_file():
        return
    
    try:
        with path_gitingest.open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        warnings.warn(f"Invalid TOML in {path_gitingest}:{exc}", UserWarning)
        return
    
    config_section = data.get("config",{})
    ignore_patterns = config_section.get("ignore_patterns")

    if not ignore_patterns:
        return
    

    if isinstance(ignore_patterns, str):
        ignore_patterns = [ignore_patterns]

    if not isinstance(ignore_patterns, (list,set)):
        warnings.warn(
            f"Expected a list/set for 'ignore_patterns',got {type(ignore_patterns)} in {path_gitingest}. Skipping.",
            UserWarning,
        )
        return
    
    ignore_patterns = set(ignore_patterns)

    valid_patterns = {pattern for pattern in ignore_patterns if isinstance(pattern, str)}
    invalid_patterns = ignore_patterns - valid_patterns

    if invalid_patterns:
        warnings.warn(f"Ignore patterns {invalid_patterns} are not strings. Skipping.", UserWarning)

    if not valid_patterns:
        return
    
    if query.ignore_patterns is None:
        query.ignore_patterns = valid_patterns
    else:
        query.ignore_patterns.update(valid_patterns)

    return

def _process_node(
        node: FileSystemNode,
        query: IngestionQuery,
        stats: FileSystemStats,
) -> None:
    """
    处理目录中的文件或目录项。

    该函数处理每个文件或目录项，根据提供的模式判断是否应包含或排除它们。它会相应地处理符号链接、
    目录和文件。

    参数
    ----------
    node : FileSystemNode
        当前正在处理的目录或文件节点。
    query : IngestionQuery
        包含仓库信息和查询参数的已解析查询对象。
    stats : FileSystemStats
        用于跟踪总文件数和大小的统计对象。
    """
    if limit_exceeded(stats, node.depth):
        return

    for sub_path in node.path.iterdir():

        if query.ignore_patterns and _should_exclude(sub_path, query.local_path, query.ignore_patterns):
            continue
        if query.include_patterns and _should_include(sub_path, query.local_path, query.include_patterns):
            continue

        if sub_path.is_symlink():
            _process_symlink(path=sub_path, parent_node=node, stats=stats, local_path=query.local_path)
        elif sub_path.is_file():
            _process_file(path=sub_path, parent_node=node,stats=stats,local_path=query.local_path)
        elif sub_path.is_dir():

            child_directory_node = FileSystemNode(
                name=sub_path.name,
                type=FileSystemNodeType.DIRECTORY,
                path_str=str(sub_path.relative_to(query.local_path)),
                path=sub_path,
                depth=node.depth + 1,
            )

            _process_node(
                node=child_directory_node,
                query=query,
                stats=stats,
            )
            node.children.append(child_directory_node)
            node.size += child_directory_node.size
            node.file_count += child_directory_node.file_count
            node.dir_count += 1 + child_directory_node.dir_count

        else:
            logger.warning("Unknown file type encountered: {}, skipping", sub_path)

    node.sort_children()

def _process_symlink(path: Path, parent_node: FileSystemNode, stats: FileSystemStats, local_path: Path) -> None:
    """
    处理文件系统中的符号链接。

    该函数检查符号链接的目标。

    参数
    ----------
    path : Path
        符号链接的完整路径。
    Parent_node : FileSystemNode
        父目录节点。
    stats : FileSystemStats
        用于跟踪总文件数和大小的统计对象。
    local_path : Path
        正在处理的仓库或目录的基础路径。
    """
    child = FileSystemNode(
        name=path.name,
        type=FileSystemNodeType.SYMLINK,
        path_str=str(path.relative_to(local_path)),
        path=path,
        depth=parent_node.depth + 1,
    )
    stats.total_files += 1
    parent_node.children.append(child)
    parent_node.file_count += 1

def _process_file(path: Path, parent_node: FileSystemNode,stats: FileSystemStats, local_path: Path) -> None:
    """
    处理文件系统中的文件。

    该函数检查文件的大小，递增统计信息，并读取文件内容。
    如果文件大小超过允许的最大值，则会抛出错误。

    参数
    ----------
    path : Path
        文件的完整路径。
    parent_node : FileSystemNode
        用于累积结果的字典。
    stats : FileSystemStats
        用于跟踪总文件数和大小的统计对象。
    local_path : Path
        正在处理的仓库或目录的基础路径。
    """
    file_size = path.stat().st_size
    if stats.total_size + file_size > MAX_TOTAL_SIZE_BYTES:
        logger.warning("Skipping file {}: would exceed total size limit ({:.1f} MB)", path, MAX_TOTAL_SIZE_BYTES / 1024 / 1024)
        return
    stats.total_files += 1
    stats.total_size += file_size

    if stats.total_files > MAX_FILES:
        logger.warning("Maximum file limit ({}) reached", MAX_FILES)
        return
    
    child = FileSystemNode(
        name=path.name,
        type=FileSystemNodeType.FILE,
        size=file_size,
        file_count=1,
        path_str=str(path.relative_to(local_path)),
        path=path,
        depth=parent_node.depth + 1, 
    )

    parent_node.children.append(child)
    parent_node.size +=file_size
    parent_node.file_count += 1

def limit_exceeded(stats: FileSystemStats, depth: int) -> bool:
    """
    检查遍历限制是否已超过。

    该函数检查当前遍历是否已超过任何配置的限制：
    最大目录深度、最大文件数或最大总大小（字节）。

    参数
    ----------
    stats : FileSystemStats
        用于跟踪总文件数和大小的统计对象。
    depth : int
        当前目录遍历的深度。

    返回
    -------
    bool
        如果任何限制已被超过则为 True，否则为 False。
    """

    if depth > MAX_DIRECTORY_DEPTH:
        logger.warning("Maximum depth limit ({}) reached", MAX_DIRECTORY_DEPTH)
        return True
    if stats.total_files >= MAX_FILES:
        logger.warning("Maximum file limit ({}) reached", MAX_FILES)
        return True
    if stats.total_size >= MAX_TOTAL_SIZE_BYTES:
        logger.warning("Maximum total size limit ({:.1f} MB) reached", MAX_TOTAL_SIZE_BYTES / 1024 / 1024)
        return True
    
    return False


