from pathlib import Path
import tempfile

MAX_FILE_SIZE = 10 * 1024 * 1024 # 10MB
MAX_DIRECTORY_DEPTH = 20
MAX_FILES = 10_000
MAX_TOTAL_SIZE_BYTES = 500 * 1024 * 1024
OUTPUT_FILE_NAME = 'digest.txt'

TMP_BASE_PATH = Path(tempfile.gettempdir()) / "gitingest"

SEPARATOR = "=" * 48
