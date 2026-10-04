"""Gitingest 包的自定义异常。"""

class InvalidNotebookError(Exception):
    """当 Jupyter notebook 无效或无法处理时引发的异常。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)



class InvalidPatternError(ValueError):
    """
    当模式（pattern）包含无效字符时引发的异常。
    该异常用于表示某个操作所提供的模式包含不允许的字符。模式中允许的字符
    包括字母数字字符、短横线（-）、下划线（_）、点（.）、正斜杠（/）、
    加号（+）和星号（*）。
    参数
    ----------
    pattern : str
        导致错误的无效模式。
    """

    def __init__(self,pattern:str) -> None:
        super().__init__(
            f" Pattern '{pattern}' contains invalid characters.Only alphanumeric characters,dash(-)," 
            "underscore (_), dot (.), forward slash (/), plus (+), and asterisk (*) are allowed."
        )

class AsyncTimeoutError(Exception):
    """
    当异步操作超过其超时限制时引发的异常。

    该异常由 `async_timeout` 装饰器使用，用于表示被包装的异步函数
    执行已超过指定的时间限制。
    """