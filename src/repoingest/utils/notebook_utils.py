"""处理 Jupyter notebook 的工具函数。"""
import json
import warnings
from itertools import chain
from pathlib import Path
from typing import Any, Dict, List, Optional

from repoingest.utils.exceptions import InvalidNotebookError


def process_notebook(file: Path,include_output: bool = True) -> str:
    """
    处理 Jupyter notebook 文件，并将可执行的 Python 脚本作为字符串返回。

    参数
    ----------
    file : Path
        Jupyter notebook 文件的路径。
    include_output : bool
        是否在生成的脚本中包含单元格输出，默认为 True。

    返回
    -------
    str
        可执行的 Python 脚本字符串。

    异常
    ------
    InvalidNotebookError
        如果 notebook 文件无效或无法处理。
    """
    try:
        with file.open(encoding="utf-8") as f:
            notebook: Dict[str, Any] = json.load(f)
    except json.JSONDecodeError as exc:
        raise InvalidNotebookError(f"Invalid JSON in notebook: {file}") from exc
    
    worksheets = notebook.get("worksheets")
    if worksheets:
        warnings.warn(
            "Worksheets are deprecated as of IPEP-17. Consider updating the notebook."
            "(See : https://github.com/jupyter/nbformat and "
            "https://github.com/ipython/ipython/wiki/IPEP-17:-Notebook-Format-4#remove-multiple-worksheets "
            "for more information.)",
            DeprecationWarning,
        )

        if len(worksheets) > 1:
            warnings.warn("Multiple worksheets detected. Combining all worksheets into a single script.", UserWarning)
        
        cells = list(chain.from_iterable(ws["cells"] for ws in worksheets))
    else:
        cells = notebook["cells"]
    
    result = ["#Jupter notebook converted to python script."]

    for cell in cells:
        cell_str = _process_cell(cell, include_output=include_output)
        if cell_str:
            result.append(cell_str)

    return "\n\n".join(result) + "\n"

def _process_cell(cell: Dict[str, Any], include_output: bool) -> Optional[str]:
    """
    处理 Jupyter notebook 单元格，并将单元格内容作为字符串返回。

    参数
    ----------
    cell : Dict[str, Any]
        来自 Jupyter notebook 的单元格字典。
    include_output: bool
        是否在生成的脚本中包含单元格输出。

    返回
    -------
    str, optional
        单元格内容字符串，若单元格为空则返回 None。

    异常
    ------
    ValueError
        如果遇到意外的单元格类型。
    """
    cell_type = cell["cell_type"]

    if cell_type not in ("markdown", "code", "raw"):
        raise ValueError(f"Unknown cell type: {cell_type}")
    
    cell_str = "".join(cell["source"])

    if not cell_str:
        return None
    
    if cell_type in ("markdown", "raw"):
        return f'"""\n{cell_str}"""'

    outputs = cell.get('outputs')
    if include_output and outputs:

        output_lines = []

        for output in outputs:
            output_lines += _extract_output(output)

        for output_line in output_lines:
            if not output_line.endswith("\n"):
                output_line += "\n"

        cell_str += "\n# Output:\n#    " + "\n#    ".join(output_lines)
    
    return cell_str

def _extract_output(output: Dict[str, Any]) -> List[str]:
    """
    从 Jupyter notebook 单元格中提取输出。

    参数
    ----------
    output : Dict[str, Any]
        Jupyter notebook 单元格的输出字典。

    返回
    -------
    List[str]
        输出字符串的列表。

    异常
    ------
    ValueError
        如果遇到未知的输出类型。
    """
    output_type = output["output_type"]

    if output_type == "stream":
        return output["text"]
    
    if output_type in ("execute_result", "display_data"):
        return output["data"]["text/plain"]
    
    if output_type == "error":
        return [f"Error: {output['ename']}:{output['evalue']}"]
    raise ValueError(f"Unknown output type: {output_type}")