"""
crawler.py - Walk directories and collect file metadata.

Responsibilities:
- Recursively walk a directory tree
- Skip excluded directories (e.g. .git, node_modules)
- Yield file metadata: path, size, modified time
"""

import os
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
from typing import Iterator, Set


@dataclass
class FileInfo:
    """Metadata about a single file."""
    path: Path
    size: int              # bytes
    modified: datetime

    def __repr__(self):
        return f"FileInfo({self.path.name}, {self.size:,} bytes)"


# Directories to skip by default
DEFAULT_EXCLUDES: Set[str] = {
    ".git", ".svn", ".hg",
    "node_modules", "__pycache__",
    ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache",
    "$RECYCLE.BIN", "System Volume Information",
}


def crawl(
    root: Path,
    exclude_dirs: Set[str] | None = None,
    min_size: int = 1,
) -> Iterator[FileInfo]:
    """
    Walk *root* and yield a FileInfo for every regular file.

    Args:
        root:         Directory to start from.
        exclude_dirs: Directory names to skip (merged with defaults).
        min_size:     Ignore files smaller than this (bytes). Default 1 (skip empty).

    Yields:
        FileInfo objects for each qualifying file.
    """
    excludes = DEFAULT_EXCLUDES | (exclude_dirs or set())

    for dirpath, dirnames, filenames in os.walk(root):
        # prune excluded dirs *in place* so os.walk won't descend into them
        dirnames[:] = [d for d in dirnames if d not in excludes]

        for fname in filenames:
            full_path = Path(dirpath) / fname

            try:
                stat = full_path.stat()
            except (OSError, PermissionError):
                continue  # can't read → skip silently

            # skip non-regular files (symlinks, etc.) and tiny files
            if not full_path.is_file() or stat.st_size < min_size:
                continue

            yield FileInfo(
                path=full_path,
                size=stat.st_size,
                modified=datetime.fromtimestamp(stat.st_mtime),
            )
