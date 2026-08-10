import asyncio
import inspect
import shutil
from typing import Optional, Union, Set, Tuple

from gitingest.cloning import clone_repo
from gitingest.config import TMP_BASE_PATH
from gitingest.ingestion import ingest_query
from gitingest.query_parsing import IngestionQuery, parse_query

async def ingest_async(
    source: str,
    max_file_size: int = 10 * 1024 * 1024,
    include_patterns: Optional[Union[str,Set[str]]] = None,
    exclude_patterns: Optional[Union[str,Set[str]]] = None,
    branch: Optional[str] = None,
    output: Optional[str] = None,
) -> Tuple[str,str,str]:
    '''
    摄取来源并处理其内容的主入口函数。

    该函数分析来源（URL 或本地路径），克隆对应的仓库（如果适用），并根据指定的查询参数处理其文件。
    它返回一个摘要、文件的树状结构以及文件内容。结果可以按需写入输出文件。

    参数
    ----------
    source : str
        要分析的来源，可以是 URL（针对 Git 仓库）或本地目录路径。
    max_file_size : int
        文件摄取允许的最大文件大小。大于此大小的文件将被忽略，默认值为
        10*1024*1024（10 MB）。
    include_patterns : Union[str, Set[str]], optional
        指定包含哪些文件的单个模式或模式集合。如果为 `None`，则包含所有文件。
    exclude_patterns : Union[str, Set[str]], optional
        指定排除哪些文件的单个模式或模式集合。如果为 `None`，则不排除任何文件。
    branch : str, optional
        要克隆和摄取的分支。如果为 `None`，则使用默认分支。
    output : str, optional
        摘要和内容要写入的文件路径。如果为 `None`，则结果不会写入文件。

    返回
    -------
    Tuple[str, str, str]
        一个包含以下内容的元组：
        - 所分析仓库或目录的摘要字符串。
        - 文件结构的树状字符串表示。
        - 仓库或目录中文件的内容。

    异常
    ------
    TypeError
        如果 `clone_repo` 未返回协程，或 `source` 为不支持的类型。    

    '''
    repo_cloned = False
    try:
        query: IngestionQuery = await parse_query(
            source=source,
            max_file_size=max_file_size,
            from_web=False,
            include_patterns=include_patterns,
            ignore_patterns=exclude_patterns,
        )

        if query.url:
            selected_branch = branch if branch else query.branch
            query.branch = selected_branch

            clone_config = query.extract_clone_config()
            clone_coroutine = clone_repo(clone_config)

            if inspect.iscoroutine(clone_coroutine):
                if asyncio.get_event_loop().is_running():
                    await clone_coroutine
                else:
                    asyncio.run(clone_coroutine)
            else:
                raise TypeError("clone_repo did not return a coroutine as expected.")

            repo_cloned = True

        summary, tree, content = ingest_query(query)

        if output is not None:
            with open(output, "w",encoding="utf-8") as f:
                f.write(tree + "\n" + content)
        
        return summary, tree, content

    finally:

        if repo_cloned:
            shutil.rmtree(TMP_BASE_PATH, ignore_errors=True) 


def  ingest(
    source: str,
    max_file_size: int = 10 * 1024 * 1024,
    include_patterns: Optional[Union[str,Set[str]]] = None,
    exclude_patterns: Optional[Union[str,Set[str]]] = None,
    branch: Optional[str] = None,
    output: Optional[str] = None,
) -> Tuple[str,str,str]:
    """
    ingest_async 的同步版本。

    该函数分析来源（URL 或本地路径），克隆对应的仓库（如果适用），并根据指定的查询参数处理其文件。
    它返回一个摘要、文件的树状结构以及文件内容。结果可以按需写入输出文件。

    参数
    ----------
    source : str
        要分析的来源，可以是 URL（针对 Git 仓库）或本地目录路径。
    max_file_size : int
        文件摄取允许的最大文件大小。大于此大小的文件将被忽略，默认值为
        10*1024*1024（10 MB）。
    include_patterns : Union[str, Set[str]], optional
        指定包含哪些文件的单个模式或模式集合。如果为 `None`，则包含所有文件。
    exclude_patterns : Union[str, Set[str]], optional
        指定排除哪些文件的单个模式或模式集合。如果为 `None`，则不排除任何文件。
    branch : str, optional
        要克隆和摄取的分支。如果为 `None`，则使用默认分支。
    output : str, optional
        摘要和内容要写入的文件路径。如果为 `None`，则结果不会写入文件。

    返回
    -------
    Tuple[str, str, str]
        一个包含以下内容的元组：
        - 所分析仓库或目录的摘要字符串。
        - 文件结构的树状字符串表示。
        - 仓库或目录中文件的内容。

    另请参阅
    --------
    ingest_async : 该函数的异步版本。
    """
    return asyncio.run(
        ingest_async(
            source=source,
            max_file_size=max_file_size,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            branch=branch,
            output=output,
        )
    )
