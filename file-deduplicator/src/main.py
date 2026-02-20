"""
main.py - CLI entry point for the File Deduplicator + Semantic Search.

Commands:
    python -m src.main scan   <directory>   Find exact duplicates  (Phase 1)
    python -m src.main index  <directory>   Index files for search (Phase 3)
    python -m src.main search <query>       Semantic search        (Phase 3)
"""

import sys
import os
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    os.system("")
    sys.stdout.reconfigure(encoding="utf-8")

from . import scanner, indexer


# ── ANSI colours ─────────────────────────────────────────
BOLD    = "\033[1m"
GREEN   = "\033[92m"
CYAN    = "\033[96m"
YELLOW  = "\033[93m"
RED     = "\033[91m"
DIM     = "\033[2m"
MAGENTA = "\033[95m"
RESET   = "\033[0m"


def _print_progress(phase: str, count: int, msg: str):
    """Live progress line."""
    icons = {
        "crawl": "[scan]", "partial": "[fast]", "full": "[hash]",
        "check": "[  ok]", "setup": "[  db]", "extract": "[read]",
        "embed": "[  ai]", "done": "[done]",
    }
    icon = icons.get(phase, "[...]")
    print(f"\r  {icon}  {msg}".ljust(80), end="", flush=True)


def _print_usage():
    print()
    print(f"  {BOLD}File Deduplicator + Semantic Search  v2.0{RESET}")
    print()
    print(f"  {BOLD}Commands:{RESET}")
    print(f"    {CYAN}scan{RESET}   <directory>         Find exact duplicate files")
    print(f"    {CYAN}index{RESET}  <directory>         Index files for semantic search")
    print(f"    {CYAN}search{RESET} <query>             Search your files by meaning")
    print()
    print(f"  {BOLD}Examples:{RESET}")
    print(f"    python -m src.main scan   C:\\Users\\admin\\Downloads")
    print(f"    python -m src.main index  C:\\Users\\admin\\Downloads")
    print(f'    python -m src.main search "receipt for the blue chair"')
    print()


# ── scan command (Phase 1) ───────────────────────────────

def cmd_scan(args: list[str]):
    """Handle 'scan' command - find exact duplicates."""
    if not args:
        print(f"  {RED}Error:{RESET} Please provide a directory to scan.")
        _print_usage()
        sys.exit(1)

    target = Path(args[0])

    if not target.is_dir():
        print(f"  {RED}Error:{RESET} '{target}' is not a directory.")
        sys.exit(1)

    print()
    print(f"  {BOLD}+--------------------------------------------+{RESET}")
    print(f"  {BOLD}|   File Deduplicator  v2.0                  |{RESET}")
    print(f"  {BOLD}+--------------------------------------------+{RESET}")
    print()
    print(f"  Scanning: {CYAN}{target}{RESET}")
    print()

    result = scanner.scan(target, progress=_print_progress)
    print()
    print()

    total  = result["total_files"]
    dupes  = result["duplicate_files"]
    groups = result["duplicate_groups"]
    wasted = result["wasted_human"]

    print(f"  {BOLD}-- Scan Results --------------------------{RESET}")
    print()
    print(f"  Total files scanned:   {BOLD}{total:,}{RESET}")
    print(f"  Exact duplicate groups:{BOLD}{groups:,}{RESET}")
    print(f"  Identical files:       {BOLD}{dupes:,}{RESET}")
    print(f"  Space you can save:    {BOLD}{GREEN}{wasted}{RESET}")
    print()

    if result["groups"]:
        print(f"  {BOLD}-- Duplicate Groups ----------------------{RESET}")
        print()

        sorted_groups = sorted(
            result["groups"],
            key=lambda g: (len(g) - 1) * g[0]["size"],
            reverse=True,
        )

        for i, group in enumerate(sorted_groups[:10], 1):
            size = group[0]["size"]
            count = len(group)
            waste = (count - 1) * size
            waste_h = scanner._human_size(waste)
            print(f"  {YELLOW}Group {i}{RESET}  ({count} copies, {waste_h} wasted)")
            for f in group:
                print(f"    {DIM}-{RESET} {f['path']}")
            print()

        remaining = len(sorted_groups) - 10
        if remaining > 0:
            print(f"  {DIM}... and {remaining} more groups.{RESET}")
            print()

    if dupes:
        print(f"  {BOLD}{GREEN}Found {dupes:,} identical files. You can save {wasted}.{RESET}")
    else:
        print(f"  {BOLD}{GREEN}No duplicates found. Your files are clean!{RESET}")
    print()


# ── index command (Phase 3) ──────────────────────────────

def cmd_index(args: list[str]):
    """Handle 'index' command - index files for semantic search."""
    if not args:
        print(f"  {RED}Error:{RESET} Please provide a directory to index.")
        _print_usage()
        sys.exit(1)

    target = Path(args[0])

    if not target.is_dir():
        print(f"  {RED}Error:{RESET} '{target}' is not a directory.")
        sys.exit(1)

    print()
    print(f"  {BOLD}+--------------------------------------------+{RESET}")
    print(f"  {BOLD}|   Semantic Search Indexer  v2.0             |{RESET}")
    print(f"  {BOLD}+--------------------------------------------+{RESET}")
    print()
    print(f"  Indexing: {CYAN}{target}{RESET}")
    print(f"  Model:   {CYAN}{indexer.EMBED_MODEL}{RESET}")
    print()

    try:
        result = indexer.index_directory(target, progress=_print_progress)
    except RuntimeError as e:
        print()
        print(f"\n  {RED}Error:{RESET} {e}")
        sys.exit(1)

    print()
    print()

    files_ok   = result["files_indexed"]
    files_skip = result["files_skipped"]
    chunks     = result["total_chunks"]

    print(f"  {BOLD}-- Index Results -------------------------{RESET}")
    print()
    print(f"  Files indexed:  {BOLD}{GREEN}{files_ok:,}{RESET}")
    print(f"  Files skipped:  {DIM}{files_skip:,}{RESET}")
    print(f"  Text chunks:    {BOLD}{chunks:,}{RESET}")
    print()

    if files_ok:
        print(f"  {BOLD}{GREEN}Index ready! Now search with:{RESET}")
        print(f'  {DIM}  python -m src.main search "your question here"{RESET}')
    else:
        print(f"  {YELLOW}No files could be indexed. Check the folder has readable files.{RESET}")
    print()


# ── search command (Phase 3) ─────────────────────────────

def cmd_search(args: list[str]):
    """Handle 'search' command - semantic search across indexed files."""
    if not args:
        print(f"  {RED}Error:{RESET} Please provide a search query.")
        print(f'  Example: python -m src.main search "receipt for blue chair"')
        sys.exit(1)

    query = " ".join(args)

    # Check if index exists
    chroma_path = Path(indexer.CHROMA_DIR)
    if not chroma_path.exists():
        print(f"  {RED}Error:{RESET} No search index found.")
        print(f"  Run 'index' first:  python -m src.main index <directory>")
        sys.exit(1)

    print()
    print(f"  {BOLD}+--------------------------------------------+{RESET}")
    print(f"  {BOLD}|   Semantic Search  v2.0                    |{RESET}")
    print(f"  {BOLD}+--------------------------------------------+{RESET}")
    print()
    print(f"  Query: {CYAN}\"{query}\"{RESET}")
    print()

    results = indexer.search(query, n_results=5)

    if not results:
        print(f"  {YELLOW}No results found.{RESET}")
        print(f"  Make sure you've indexed files first:")
        print(f"    python -m src.main index <directory>")
        print()
        return

    print(f"  {BOLD}-- Top {len(results)} Results -----------------------{RESET}")
    print()

    # Deduplicate by file path (show best chunk per file)
    seen_files = {}
    for hit in results:
        path = hit["path"]
        if path not in seen_files or hit["score"] > seen_files[path]["score"]:
            seen_files[path] = hit

    for rank, hit in enumerate(seen_files.values(), 1):
        score = hit["score"]

        # Color by relevance
        if score >= 80:
            color = GREEN
        elif score >= 60:
            color = YELLOW
        else:
            color = DIM

        # Truncate preview
        preview = hit["chunk_text"][:200].replace("\n", " ")
        if len(hit["chunk_text"]) > 200:
            preview += "..."

        print(f"  {BOLD}{rank}.{RESET} {color}[{score}% match]{RESET}  {hit['file_type'].upper()}")
        print(f"     {CYAN}{hit['path']}{RESET}")
        print(f"     {DIM}{preview}{RESET}")
        print()

    # Offer to open the best match
    best = results[0]
    best_path = Path(best["path"])
    if best_path.exists():
        print(f"  {BOLD}Best match:{RESET} {best_path.name}")
        print(f"  {DIM}Open it with:{RESET}")
        if sys.platform == "win32":
            escaped = str(best_path).replace('"', '\\"')
            print(f'    start "" "{escaped}"')
        else:
            print(f"    open \"{best_path}\"")
        print()


# ── entry point ──────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        _print_usage()
        sys.exit(1)

    command = sys.argv[1].lower()
    args = sys.argv[2:]

    if command == "scan":
        cmd_scan(args)
    elif command == "index":
        cmd_index(args)
    elif command == "search":
        cmd_search(args)
    else:
        print(f"  {RED}Unknown command:{RESET} '{command}'")
        _print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
