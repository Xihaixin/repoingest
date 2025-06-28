"""
Test for the `query_ingestion` module.

These tests validate directory scanning, file content extraction, notebook handling, and the overall ingestion logic,
including filtering patterns and subpaths.
"""

from pathlib import Path

from gitingest.ingestion import ingest_query
from gitingest.query_parsing import IngestionQuery

def test_run_ingest_query(temp_directory: Path, sample_query: IngestionQuery) -> None:
    """
    
    """
    sample_query.local_path = temp_directory
    sample_query.subpath = "/"
    sample_query.type = None

    summary, _, content = ingest_query(sample_query)

    assert "Repsoitory: test_user/test_repo" in summary
    assert "File analyzed: 8" in summary

    # Check presence of key files in the content
    assert "src.subfile1.txt" in content
    assert "src/subfile2.txt" in content
    assert "src/subdir/file_subdir.txt" in content
    assert "src/subdir/file_subdir.py" in content
    assert "file1.txt" in content
    assert "file2.py" in content
    assert "dir1/file_dir1.txt" in content
    assert "dir1/file_dir2.txt" in content


# TODO: Additional tests:
# - Multiple include patterns, e.g. ["*.txt", "*.py"] or ["/src/*", "*.txt"].
# - Edge cases with weird file names or deep subdirectory structures.
# TODO : def test_include_txt_pattern
# TODO : def test_include_nonexistent_extension


