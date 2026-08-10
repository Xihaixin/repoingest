import os
import tempfile
import platform
from pathlib import Path

from dotenv import load_dotenv

from gitingest.utils.logger import get_logger

logger = get_logger("config")

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_DIRECTORY_DEPTH = 20
MAX_FILES = 10_000
MAX_TOTAL_SIZE_BYTES = 500 * 1024 * 1024
OUTPUT_FILE_NAME = "digest.txt"

SEPARATOR = "=" * 48

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)


def get_temp_base_path() -> Path:
    """获取克隆仓库的基础临时目录路径。"""
    if platform.system() == "Windows":
        custom_tmp_path = os.getenv("GITINGEST_TMP_PATH")
        if not custom_tmp_path:
            logger.warning(
                "Environment variable 'GITINGEST_TMP_PATH' not set, "
                "using system temporary directory."
            )
            tmp_base = Path(tempfile.gettempdir()) / "gitingest"
        else:
            tmp_base = Path(custom_tmp_path) / "gitingest"
    else:
        tmp_base = Path(tempfile.gettempdir()) / "gitingest"

    # 确保临时目录存在
    tmp_base.mkdir(parents=True, exist_ok=True)

    # 针对不同平台设置权限
    if platform.system() == "Windows":
        os.chmod(tmp_base, 0o777)
    else:
        os.chmod(tmp_base, 0o755)

    return tmp_base


TMP_BASE_PATH = get_temp_base_path()