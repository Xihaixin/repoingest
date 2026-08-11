import locale
import platform
from typing import List
from pathlib import Path

try:
    locale.setlocale(locale.LC_ALL,"")
except locale.Error:
    locale.setlocale(locale.LC_ALL,"C")

def is_text_file(path: Path) -> bool:
    """
    通过尝试使用多种编码解码一小块内容，并检查常见的二进制标记，
    来判断文件是否可能是文本文件。

    参数
    ----------
    path : Path
        要检查的文件的路径。
    
    返回
    -------
    bool
        如果文件很可能是文本则返回 True；如果看起来是二进制则返回 False。
    """

    # 尝试以二进制模式读取文件的一部分
    try:
        with path.open("rb") as f:
            chunk = f.read(1024)
    except OSError:
        return False

    if not chunk:
        return True

    if b"\x00" in chunk or b"\xff" in chunk:
        return False

    for enc in get_preferred_encodings():
        try:
            with path.open(encoding=enc) as f:
                f.read()
                return True
        except UnicodeDecodeError:
            continue
        except UnicodeError:
            continue
        except OSError:
            return False
        
    return False

def get_preferred_encodings() -> List[str]:
    """
    获取要尝试的编码列表，并按当前平台进行优先级排序。

    返回
    -------
    List[str]
        按优先级顺序排列的要尝试的编码名称列表，以平台的默认编码开头，
        后跟常见的后备编码。
    """
    encodings = [locale.getpreferredencoding(),"utf-8","utf-16","utf-16e","utf-8-sig","latin"]
    if platform.system() == "windows":
        encodings += ["cp1252","iso-8859-1"]
    return encodings
