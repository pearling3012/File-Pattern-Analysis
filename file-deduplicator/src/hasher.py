"""
hasher.py - Compute BLAKE3 hashes for files.

Strategy (tiered hashing to minimise disk I/O):
  1. Group files by size          → different size = can't be duplicates.
  2. Partial hash (first 64 KB)   → quick filter for same-size files.
  3. Full hash (entire file)      → confirms true duplicates.

Only step 3 reads the whole file, and only for candidates that survive
steps 1 and 2.
"""

import blake3
from pathlib import Path


CHUNK_SIZE = 65_536  # 64 KB – good trade-off between speed and syscall overhead


def partial_hash(path: Path, size: int = CHUNK_SIZE) -> str:
    """
    Hash the first *size* bytes of a file.

    Returns:
        Hex-encoded BLAKE3 digest (64 chars).
    """
    hasher = blake3.blake3()

    with open(path, "rb") as f:
        chunk = f.read(size)
        hasher.update(chunk)

    return hasher.hexdigest()


def full_hash(path: Path) -> str:
    """
    Hash the entire file contents.

    Reads in 64 KB chunks so even multi-GB files won't blow up memory.

    Returns:
        Hex-encoded BLAKE3 digest (64 chars).
    """
    hasher = blake3.blake3()

    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            hasher.update(chunk)

    return hasher.hexdigest()
