import asyncio
import logging
import json
import shutil
from typing import Optional, Union, Set, Tuple

from gitingest.config import TMP_BASE_PATH
from gitingest.ingestion import ingest_query
from gitingest.query_parsing import IngestionQuery, parse_query
from gitingest.utils.logger_handler import PathEncoder

async def ingest_async(
    source: str,
    max_file_size: int = 10 * 1024 * 1024,
    include_patterns: Optional[Union[str,Set[str]]] = None,
    exclude_patterns: Optional[Union[str,Set[str]]] = None,
    branch: Optional[str] = None,
    output: Optional[str] = None,
) -> Tuple[str,str,str]:
    '''
    Main entry point for ingesting a source and processing its contents.

    This function annlyzes a source (URL or local path), clones the corresponding repository (if applicable),
    and processes its files according to the specified query parameters. It returns a summary, a tree-like
    structure of the files, and the content of the files. The results can optionally be written to an output file.

    Parameters
    ----------
    source : str
        The source to analyze, which can be a URL (for a Git repository) or a local directory path.
    max_file_size : int
        Maximum allowed file size for file ingestion. Files larger than this size are ignored, by default
        10*1024*1024 (10 MB).
    include_patterns : Union[str, Set[str]], optional
        Pattern or set of patterns specifying which files to include. If `None`, all files are included.
    exclude_patterns : Union[str, Set[str]], optional
        Pattern or set of patterns specifying which files to exclude. If `None`, no files are excluded.
    branch : str, optional
        The branch to clone and ingest. If `None`, the default branch is used.
    output : str, optional
        File path where the summary and content should be written. If `None`, the results are not written to a file.

    Returns
    -------
    Tuple[str, str, str]
        A tuple containing:
        - A summary string of the analyzed repository or directory.
        - A tree-like string representation of the file structure.
        - The content of the files in the repository or directory.

    Raises
    ------
    TypeError
        If `clone_repo` does not return a coroutine, or if the `source` is of an unsupported type.    

    '''
    logging.info(f"Origin 'source':{source}")
    repo_cloned = False
    try:
        query: IngestionQuery = await parse_query(
            source=source,
            max_file_size=max_file_size,
            from_web=False,
            include_patterns=include_patterns,
            ignore_patterns=exclude_patterns,
        )
        log_dict ={
            "event": "Parameters",
            "url": query.url,
            "source": source,
            "local_path": query.local_path,
            "id": query.id,
            "subpath": query.subpath,
            "type": query.type
        }
        logging.info(f"Begin to parsed the parameters:\n {json.dumps(log_dict,indent=2, cls=PathEncoder)}")
        logging.info(f"The parameter 'source' has been handled in parse_query by _parse_local_dir_path, which was translated to slug : \n {query.slug} ")

        if False:

            repo_cloned = True

        summary, tree, content = ingest_query(query)

        if output is not None:
            with open(output, "w",encoding="utf-8") as f:
                f.write(tree + "\n" + content)
        
        return summary, tree, content

    finally:

        if repo_cloned:
            shutil.rmtree(TMP_BASE_PATH, ignore_error=True) 


def  ingest(
    source: str,
    max_file_size: int = 10 * 1024 * 1024,
    include_patterns: Optional[Union[str,Set[str]]] = None,
    exclude_patterns: Optional[Union[str,Set[str]]] = None,
    branch: Optional[str] = None,
    output: Optional[str] = None,
) -> Tuple[str,str,str]:
    """
    Synchronous version of ingest_async.

    This function analyzes a source (URL or local path), clones the corresponding repository (if applicable),
    and processes its files according to the specified query parameters. It returns a summary, a tree-like
    structure of the files, and the content of the files. The results can optionally be written to an output file.

    Parameters
    ----------
    source : str
        The source to analyze, which can be a URL (for a Git repository) or a local directory path.
    max_file_size : int
        Maximum allowed file size for file ingestion. Files larger than this size are ignored, by default
        10*1024*1024 (10 MB).
    include_patterns : Union[str, Set[str]], optional
        Pattern or set of patterns specifying which files to include. If `None`, all files are included.
    exclude_patterns : Union[str, Set[str]], optional
        Pattern or set of patterns specifying which files to exclude. If `None`, no files are excluded.
    branch : str, optional
        The branch to clone and ingest. If `None`, the default branch is used.
    output : str, optional
        File path where the summary and content should be written. If `None`, the results are not written to a file.

    Returns
    -------
    Tuple[str, str, str]
        A tuple containing:
        - A summary string of the analyzed repository or directory.
        - A tree-like string representation of the file structure.
        - The content of the files in the repository or directory.

    See Also
    --------
    ingest_async : The asynchronous version of this function.
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
