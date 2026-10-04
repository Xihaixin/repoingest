"""repoingest 命令行接口。

用法示例::

    repoingest /path/to/directory
    repoingest https://github.com/Xihaixin/repoingest
    repoingest https://github.com/Xihaixin/repoingest -o -      # 输出到标准输出
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Set

import click

from repoingest import __version__
from repoingest.config import MAX_FILE_SIZE, OUTPUT_FILE_NAME
from repoingest.entrypoint import ingest
from repoingest.utils.logger import setup_logging


def _split_patterns(value: Optional[str]) -> Optional[Set[str]]:
    """把逗号分隔的模式字符串拆成集合（空值返回 ``None``）。"""
    if not value:
        return None

    patterns = {part.strip() for part in value.split(",") if part.strip()}
    return patterns or None


def _format_digest(summary: str, tree: str, content: str) -> str:
    """把摘要、目录结构与文件内容拼接成完整 digest。"""
    return f"{summary}\n\n{tree}\n\n{content}"


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version=__version__, prog_name="repoingest")
@click.argument("source")
@click.option(
    "-o",
    "--output",
    default=OUTPUT_FILE_NAME,
    show_default=True,
    help="输出文件路径；使用 '-' 输出到标准输出。",
)
@click.option(
    "--max-file-size",
    type=int,
    default=MAX_FILE_SIZE,
    show_default=True,
    help="单个文件的最大字节数，超过则跳过。",
)
@click.option(
    "--include",
    "include_patterns",
    default=None,
    help="仅包含匹配该 glob 模式的文件（逗号分隔）。",
)
@click.option(
    "--exclude",
    "exclude_patterns",
    default=None,
    help="排除匹配该 glob 模式的文件（逗号分隔）。",
)
@click.option("-b", "--branch", default=None, help="要摄取的分支（默认使用仓库默认分支）。")
def main(
    source: str,
    output: str,
    max_file_size: int,
    include_patterns: Optional[str],
    exclude_patterns: Optional[str],
    branch: Optional[str],
) -> None:
    """将 Git 仓库或本地目录转换为适合 LLM 提示的文本摘要。"""
    setup_logging(log_level="WARNING")

    try:
        summary, tree, content = ingest(
            source,
            max_file_size=max_file_size,
            include_patterns=_split_patterns(include_patterns),
            exclude_patterns=_split_patterns(exclude_patterns),
            branch=branch,
        )
    except Exception as exc:  # noqa: BLE001 - 面向用户输出友好错误
        click.echo(f"错误：{exc}", err=True)
        sys.exit(1)

    digest = _format_digest(summary, tree, content)

    if output == "-":
        click.echo(digest)
        return

    destination = Path(output)
    destination.write_text(digest, encoding="utf-8")
    click.echo(f"Digest 已写入 {destination}")


if __name__ == "__main__":  # pragma: no cover
    main()
