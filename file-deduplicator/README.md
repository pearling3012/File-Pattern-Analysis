# Sift

A native desktop file explorer with built-in duplicate detection and semantic search. Browse your files in a clean, Finder-inspired UI, find exact duplicates wasting disk space, and search documents by meaning — not just filename.

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

- **File Browser** — Navigate drives, folders, and files with keyboard shortcuts, grid/list views, and breadcrumb path bar.
- **Duplicate Scanner** — Detects exact-copy files using a multi-pass BLAKE3 hashing pipeline (size → partial hash → full hash). Shows wasted space at a glance.
- **Semantic Search** — Index documents (PDF, DOCX, TXT, images via OCR) with Ollama embeddings and ChromaDB, then search by meaning in plain English.
- **Native Window** — Frameless pywebview shell with macOS-style traffic light controls (close, minimize, fullscreen/zoom).

## Architecture

```
file-deduplicator/
├── run.py                 # Entry point — launches FastAPI + pywebview window
├── app/
│   ├── server.py          # FastAPI backend (file browsing, scan, search APIs)
│   ├── templates/         # Jinja2 HTML
│   └── static/            # CSS + JS frontend
├── src/
│   ├── crawler.py         # Recursive directory walker
│   ├── hasher.py          # BLAKE3 partial & full hashing
│   ├── database.py        # SQLite storage for file metadata
│   ├── scanner.py         # Duplicate detection pipeline
│   ├── reader.py          # Text extraction (PDF, DOCX, images, plain text)
│   ├── indexer.py         # Semantic indexing & search (ChromaDB + Ollama)
│   └── main.py            # CLI entry point
└── pyproject.toml
```

## Requirements

- **Python 3.11+**
- **Ollama** running locally (for semantic search only) with the `nomic-embed-text` model pulled

## Setup

```bash
# Clone and enter the project
cd file-deduplicator

# Create a virtual environment and install dependencies
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

pip install -e .

# Optional: install OCR support for image text extraction
pip install -e ".[ocr]"
```

### Ollama (for semantic search)

```bash
ollama pull nomic-embed-text
ollama serve
```

## Usage

### Desktop App

```bash
python run.py
```

Opens a native window on `http://127.0.0.1:8000`. Use the sidebar to browse drives and favorites, the toolbar to switch views and filter, and the Tools section for duplicate scanning and semantic search.

**Window controls:**

| Button | Click | Alt+Click |
|--------|-------|-----------|
| Red | Close | — |
| Yellow | Minimize | — |
| Green | Fullscreen | Zoom (maximize/restore) |

### CLI

```bash
# Scan for duplicates
dedup scan C:\Users\admin\Documents

# Index a folder for semantic search
dedup index C:\Users\admin\Documents

# Search indexed files
dedup search "meeting notes about project timeline"
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Vanilla JS, CSS (Finder-style) |
| Backend | FastAPI, Uvicorn |
| Desktop shell | pywebview (frameless) |
| Hashing | BLAKE3 |
| Database | SQLite |
| Embeddings | Ollama (`nomic-embed-text`) |
| Vector store | ChromaDB |
| Text extraction | PyMuPDF, python-docx, EasyOCR |
