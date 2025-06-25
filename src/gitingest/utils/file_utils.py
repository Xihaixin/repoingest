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
    Determine if the file is likely a text file by typing to decode a small chunk
    with multiple encodings, and checking for common binary markers.

    Parameters
    ----------
    path : Path
        The path to the file to check.
    
    Returns
    -------
    bool
        True if the file is likely textual; False if it appears to be binary.
    """

    # Attempt to read a portion of the file in binary mode
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
    Get list of encodings to try, prioritized for the current platform.

    Returns
    -------
    List[str]
        List of encoding names to try in priority order, starting with the
        platform's default encoding followed by common fallback encodings.
    """
    encodings = [locale.getpreferredencoding(),"utf-8","utf-16","utf-16e","utf-8-sig","latin"]
    if platform.system() == "windows":
        encodings += ["cp1252","iso-8859-1"]
    return encodings
