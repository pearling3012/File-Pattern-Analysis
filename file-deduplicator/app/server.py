"""
server.py - FastAPI backend for the Finder-like file explorer.

Serves:
  - File browsing API (list files, drives, open files)
  - Duplicate scanner API (scan, get results)
  - Semantic search API (index, search)
  - Static frontend (Finder-like UI)
"""

import os
import sys
import subprocess
import string
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, Query
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

# Add project root to path so we can import src modules
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src import scanner, indexer, reader

app = FastAPI(title="File Explorer", version="2.0")

# Static files & templates
APP_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


# ── Helpers ──────────────────────────────────────────────

def _human_size(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} PB"


def _file_icon(path: Path, is_dir: bool) -> str:
    if is_dir:
        return "folder"
    ext = path.suffix.lower()
    if ext in reader.PDF_EXTENSIONS:
        return "pdf"
    elif ext in reader.IMAGE_EXTENSIONS:
        return "image"
    elif ext in reader.DOCX_EXTENSIONS:
        return "doc"
    elif ext in reader.TEXT_EXTENSIONS:
        return "text"
    elif ext in {".zip", ".rar", ".7z", ".tar", ".gz"}:
        return "archive"
    elif ext in {".exe", ".msi", ".bat", ".cmd"}:
        return "app"
    elif ext in {".mp4", ".avi", ".mkv", ".mov", ".wmv"}:
        return "video"
    elif ext in {".mp3", ".wav", ".flac", ".aac", ".ogg"}:
        return "audio"
    return "file"


def _get_file_info(path: Path) -> Optional[dict]:
    try:
        stat = path.stat()
        is_dir = path.is_dir()
        return {
            "name": path.name,
            "path": str(path),
            "is_dir": is_dir,
            "size": stat.st_size if not is_dir else None,
            "size_human": _human_size(stat.st_size) if not is_dir else "--",
            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%b %d, %Y  %H:%M"),
            "icon": _file_icon(path, is_dir),
            "extension": path.suffix.lower() if not is_dir else "",
        }
    except (OSError, PermissionError):
        return None


# ── Page routes ──────────────────────────────────────────

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ── File browsing API ────────────────────────────────────

@app.get("/api/drives")
async def get_drives():
    """List available drives (Windows) or root (Linux/Mac)."""
    if sys.platform == "win32":
        drives = []
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if Path(drive).exists():
                try:
                    total, used, free = 0, 0, 0
                    import ctypes
                    free_bytes = ctypes.c_ulonglong(0)
                    total_bytes = ctypes.c_ulonglong(0)
                    ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                        drive, None, ctypes.pointer(total_bytes), ctypes.pointer(free_bytes)
                    )
                    total = total_bytes.value
                    free = free_bytes.value
                    drives.append({
                        "name": f"{letter}:",
                        "path": drive,
                        "total": total,
                        "free": free,
                        "total_human": _human_size(total),
                        "free_human": _human_size(free),
                    })
                except Exception:
                    drives.append({"name": f"{letter}:", "path": drive})
        return drives
    else:
        return [{"name": "/", "path": "/"}]


@app.get("/api/files")
async def list_files(path: str = Query(...)):
    """List files and folders in a directory."""
    target = Path(path)
    if not target.exists():
        return JSONResponse({"error": "Path not found"}, status_code=404)
    if not target.is_dir():
        return JSONResponse({"error": "Not a directory"}, status_code=400)

    items = []
    try:
        for entry in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            # Skip hidden files/system files
            if entry.name.startswith(".") or entry.name.startswith("$"):
                continue
            info = _get_file_info(entry)
            if info:
                items.append(info)
    except PermissionError:
        return JSONResponse({"error": "Permission denied"}, status_code=403)

    # Parent path
    parent = str(target.parent) if target.parent != target else None

    return {
        "current": str(target),
        "parent": parent,
        "items": items,
        "count": len(items),
    }


@app.get("/api/favorites")
async def get_favorites():
    """Return quick-access folders."""
    home = Path.home()
    favs = [
        {"name": "Desktop", "path": str(home / "Desktop"), "icon": "desktop"},
        {"name": "Downloads", "path": str(home / "Downloads"), "icon": "download"},
        {"name": "Documents", "path": str(home / "Documents"), "icon": "document"},
        {"name": "Pictures", "path": str(home / "Pictures"), "icon": "image"},
    ]
    return [f for f in favs if Path(f["path"]).exists()]


# ── File actions ─────────────────────────────────────────

class OpenRequest(BaseModel):
    path: str

@app.post("/api/open")
async def open_file(req: OpenRequest):
    """Open a file with the default system application."""
    path = Path(req.path)
    if not path.exists():
        return JSONResponse({"error": "File not found"}, status_code=404)
    try:
        if sys.platform == "win32":
            os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return {"status": "ok"}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Duplicate scanner API ────────────────────────────────

class ScanRequest(BaseModel):
    path: str

@app.post("/api/scan")
async def scan_directory(req: ScanRequest):
    """Scan a directory for exact duplicates."""
    target = Path(req.path)
    if not target.is_dir():
        return JSONResponse({"error": "Not a directory"}, status_code=400)

    try:
        result = scanner.scan(target)
        return result
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Semantic search API ──────────────────────────────────

class IndexRequest(BaseModel):
    path: str

@app.post("/api/index")
async def index_directory(req: IndexRequest):
    """Index a directory for semantic search."""
    target = Path(req.path)
    if not target.is_dir():
        return JSONResponse({"error": "Not a directory"}, status_code=400)

    try:
        result = indexer.index_directory(target)
        return result
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=503)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


class SearchRequest(BaseModel):
    query: str
    n_results: int = 5

@app.post("/api/search")
async def search_files(req: SearchRequest):
    """Semantic search across indexed files."""
    try:
        results = indexer.search(req.query, n_results=req.n_results)
        return {"results": results, "count": len(results)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Quick Look / Preview API ────────────────────────────

@app.get("/api/preview")
async def preview_file(path: str = Query(...)):
    """Return file info + text preview for Quick Look."""
    target = Path(path)
    if not target.exists():
        return JSONResponse({"error": "File not found"}, status_code=404)

    info = _get_file_info(target)
    if not info:
        return JSONResponse({"error": "Cannot read file"}, status_code=500)

    preview_text = None
    try:
        text = reader.extract_text(target)
        if text:
            preview_text = text[:3000]
    except Exception:
        pass

    info["preview_text"] = preview_text
    return info


@app.get("/api/file-content")
async def serve_file_content(path: str = Query(...)):
    """Serve raw file bytes (images, etc.) for Quick Look previews."""
    target = Path(path)
    if not target.exists():
        return JSONResponse({"error": "File not found"}, status_code=404)
    if target.is_dir():
        return JSONResponse({"error": "Cannot serve directory"}, status_code=400)
    return FileResponse(target)


@app.post("/api/reveal")
async def reveal_in_explorer(req: OpenRequest):
    """Open the containing folder and select the item in the system file manager."""
    path = Path(req.path)
    if not path.exists():
        return JSONResponse({"error": "Path not found"}, status_code=404)
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select," + str(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path.parent if path.is_file() else path)])
        return {"status": "ok"}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
