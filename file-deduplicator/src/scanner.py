"""
scanner.py - Scan pipeline.

Pipeline:
  Phase 1  crawl         → insert every file into the DB.
  Phase 2  partial hash  → hash first 64 KB for same-size files.
  Phase 3  full hash     → confirm exact duplicates.

Text extraction, MinHash, and OCR are disabled for now (too costly).
Can be re-enabled later when needed.
"""

from pathlib import Path
from typing import Callable, Optional

from . import crawler, hasher, database, reader


# Type alias for progress callbacks
ProgressFn = Callable[[str, int, str], None]


def scan(
    root: Path,
    db_path: str = database.DB_NAME,
    progress: Optional[ProgressFn] = None,
) -> dict:
    """
    Run the scan pipeline (exact duplicates only).

    Args:
        root:     Directory to scan.
        db_path:  Path to the SQLite database file.
        progress: Optional callback(phase, count, message).

    Returns:
        Summary dict.
    """
    conn = database.connect(db_path)
    database.clear_files(conn)

    def _progress(phase: str, count: int, msg: str):
        if progress:
            progress(phase, count, msg)

    # ── Phase 1: Crawl ───────────────────────────────────
    _progress("crawl", 0, "Crawling directory tree...")
    file_count = 0

    for info in crawler.crawl(root):
        ftype = reader.file_type_label(info.path)
        database.insert_file(conn, info.path, info.size, info.modified, ftype)
        file_count += 1
        if file_count % 500 == 0:
            _progress("crawl", file_count, f"Found {file_count:,} files...")

    conn.commit()
    _progress("crawl", file_count, f"Crawl done - {file_count:,} files.")

    # ── Phase 2: Partial hash ────────────────────────────
    _progress("partial", 0, "Computing partial hashes...")
    dup_sizes = database.sizes_with_duplicates(conn)
    partial_count = 0

    for size in dup_sizes:
        rows = database.files_by_size(conn, size)
        for row_id, path in rows:
            try:
                h = hasher.partial_hash(Path(path))
                database.update_partial_hash(conn, row_id, h)
                partial_count += 1
                if partial_count % 200 == 0:
                    _progress("partial", partial_count, f"Partial-hashed {partial_count:,} files...")
            except (OSError, PermissionError):
                continue

    conn.commit()
    _progress("partial", partial_count, f"Partial hashing done - {partial_count:,} files.")

    # ── Phase 3: Full hash ───────────────────────────────
    _progress("full", 0, "Computing full hashes...")
    dup_partials = database.partial_hashes_with_duplicates(conn)
    full_count = 0

    for ph in dup_partials:
        rows = database.files_by_partial_hash(conn, ph)
        for row_id, path in rows:
            try:
                h = hasher.full_hash(Path(path))
                database.update_full_hash(conn, row_id, h)
                full_count += 1
                if full_count % 100 == 0:
                    _progress("full", full_count, f"Full-hashed {full_count:,} files...")
            except (OSError, PermissionError):
                continue

    conn.commit()
    _progress("full", full_count, f"Full hashing done - {full_count:,} files.")

    # ── Results ──────────────────────────────────────────
    exact_groups = database.get_duplicate_groups(conn)
    exact_dupes = sum(len(g) - 1 for g in exact_groups)
    wasted = sum((len(g) - 1) * g[0]["size"] for g in exact_groups)

    conn.close()

    return {
        "total_files": file_count,
        "duplicate_files": exact_dupes,
        "duplicate_groups": len(exact_groups),
        "wasted_bytes": wasted,
        "wasted_human": _human_size(wasted),
        "groups": exact_groups,
    }


def _human_size(nbytes: int) -> str:
    """Convert bytes to a human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} PB"
