import os
from pathlib import Path
from dotenv import load_dotenv
import tempfile
import platform

MAX_FILE_SIZE = 10 * 1024 * 1024 # 10MB
MAX_DIRECTORY_DEPTH = 20
MAX_FILES = 10_000
MAX_TOTAL_SIZE_BYTES = 500 * 1024 * 1024
OUTPUT_FILE_NAME = 'digest.txt'

SEPARATOR = "=" * 48

src_path = Path(__file__).parent.parent
load_dotenv(dotenv_path=src_path.parent / ".env", override=True)

def get_temp_base_path() -> Path:
    if platform.system() == "Windows":
        custom_tmp_path = os.getenv("GITINGEST_TMP_PATH")
        if not custom_tmp_path:
            print("WARRING: You don't config the environment var of 'GITINGEST_TMP_PATH', use system temporary directory.")
            tmp_base = Path(tempfile.gettempdir()) / "gitingest"
        else:
            tmp_base = Path(custom_tmp_path) / "gitingest"
    else:
        tmp_base = Path(tempfile.gettempdir()) / "gitingest"
    
    # Make sure the tmp directory exist
    tmp_base.mkdir(parents=True, exist_ok=True)

    # Set permission for different platform
    if platform.system() == "Windows":
        os.chmod(tmp_base, 0o777)
    else:
        os.chmod(tmp_base, 0o755)
    
    return tmp_base

TMP_BASE_PATH = get_temp_base_path()