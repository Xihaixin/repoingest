"""
`query_ingestion` 模块的测试。

这些测试验证目录扫描、文件内容提取、notebook 处理以及整体摄取逻辑，
包括过滤模式和子路径。
"""

from pathlib import Path

from repoingest.ingestion import ingest_query
from repoingest.query_parsing import IngestionQuery

def test_run_ingest_query(temp_directory: Path, sample_query: IngestionQuery) -> None:
    """运行摄取查询并验证摘要与文件内容。"""
    sample_query.local_path = temp_directory
    sample_query.subpath = "/"
    sample_query.type = None

    summary, _, content = ingest_query(sample_query)

    assert "Repository: test_user/test_repo" in summary
    assert "Files analyzed: 8" in summary

    # 检查内容中是否存在关键文件
    assert "src.subfile1.txt" in content
    assert "src/subfile2.txt" in content
    assert "src/subdir/file_subdir.txt" in content
    assert "src/subdir/file_subdir.py" in content
    assert "file1.txt" in content
    assert "file2.py" in content
    assert "dir1/file_dir1.txt" in content
    assert "dir1/file_dir2.txt" in content


# TODO: 附加测试：
# - 多个 include 模式，例如 ["*.txt", "*.py"] 或 ["/src/*", "*.txt"]。
# - 异常文件名或深层子目录结构等边界情况。
# TODO : def test_include_txt_pattern
# TODO : def test_include_nonexistent_extension


