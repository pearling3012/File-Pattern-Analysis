"""
database.py - SQLite storage for file metadata and hashes.

Schema
------
files  – one row per scanned file
"""

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Tuple


DB_NAME = "deduplicator.db"


def connect(db_path: str = DB_NAME) -> sqlite3.Connection:
    """Open (or create) the database and ensure tables exist."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    _create_tables(conn)
    return conn


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS files (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            path          TEXT    NOT NULL,
            size          INTEGER NOT NULL,
            modified      TEXT    NOT NULL,
            file_type     TEXT,
            hash_partial  TEXT,
            hash_full     TEXT,
            scanned_at    TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_files_size
            ON files(size);
        CREATE INDEX IF NOT EXISTS idx_files_hash_partial
            ON files(hash_partial);
        CREATE INDEX IF NOT EXISTS idx_files_hash_full
            ON files(hash_full);
    """)
    conn.commit()


# ── writes ──────────────────────────────────────────────

def insert_file(
    conn: sqlite3.Connection,
    path: Path,
    size: int,
    modified: datetime,
    file_type: str = "",
) -> int:
    """Insert a file record (no hashes yet). Returns the row id."""
    cur = conn.execute(
        "INSERT INTO files (path, size, modified, file_type) VALUES (?, ?, ?, ?)",
        (str(path), size, modified.isoformat(), file_type),
    )
    return cur.lastrowid


def update_partial_hash(conn: sqlite3.Connection, row_id: int, h: str) -> None:
    conn.execute("UPDATE files SET hash_partial = ? WHERE id = ?", (h, row_id))


def update_full_hash(conn: sqlite3.Connection, row_id: int, h: str) -> None:
    conn.execute("UPDATE files SET hash_full = ? WHERE id = ?", (h, row_id))


def clear_files(conn: sqlite3.Connection) -> None:
    """Delete all file records (fresh scan)."""
    conn.execute("DELETE FROM files")
    conn.commit()


# ── reads ───────────────────────────────────────────────

def count_files(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]


def sizes_with_duplicates(conn: sqlite3.Connection) -> List[int]:
    """Return file sizes that appear more than once."""
    rows = conn.execute(
        "SELECT size FROM files GROUP BY size HAVING COUNT(*) > 1"
    ).fetchall()
    return [r[0] for r in rows]


def files_by_size(conn: sqlite3.Connection, size: int) -> List[Tuple[int, str]]:
    """Return (id, path) for all files of a given size."""
    return conn.execute(
        "SELECT id, path FROM files WHERE size = ?", (size,)
    ).fetchall()


def partial_hashes_with_duplicates(conn: sqlite3.Connection) -> List[str]:
    """Return partial hashes that appear more than once."""
    rows = conn.execute(
        """SELECT hash_partial
           FROM files
           WHERE hash_partial IS NOT NULL
           GROUP BY size, hash_partial
           HAVING COUNT(*) > 1"""
    ).fetchall()
    return [r[0] for r in rows]


def files_by_partial_hash(conn: sqlite3.Connection, h: str) -> List[Tuple[int, str]]:
    """Return (id, path) for all files with a given partial hash."""
    return conn.execute(
        "SELECT id, path FROM files WHERE hash_partial = ?", (h,)
    ).fetchall()


def get_duplicate_groups(conn: sqlite3.Connection) -> List[List[dict]]:
    """
    Return exact duplicate groups.
    Each group is a list of dicts: {path, size, modified, hash_full}.
    Only groups with 2+ files are returned.
    """
    rows = conn.execute(
        """SELECT hash_full, path, size, modified
           FROM files
           WHERE hash_full IS NOT NULL
           ORDER BY hash_full"""
    ).fetchall()

    groups: dict[str, list] = {}
    for hash_full, path, size, modified in rows:
        groups.setdefault(hash_full, []).append({
            "path": path,
            "size": size,
            "modified": modified,
            "hash": hash_full,
        })

    return [g for g in groups.values() if len(g) >= 2]
