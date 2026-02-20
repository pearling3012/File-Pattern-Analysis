"""
reader.py - Text extraction from files + file type labelling.

Extraction is used ONLY by the semantic search indexer (Phase 3).
The duplicate scanner (Phase 1) only uses file_type_label().

Supported formats:
  - Plain text (.txt, .md, .py, .js, .csv, .json, etc.)
  - PDF        (.pdf)  → via pymupdf
  - Images     (.png, .jpg, etc.) → via easyocr (GPU if available)
  - Word       (.docx) → via python-docx

Each reader returns plain text, or None if unsupported/unreadable.
"""

from pathlib import Path
from typing import Optional


# ── file-type sets ───────────────────────────────────────

TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst", ".csv", ".tsv", ".json",
    ".xml", ".html", ".htm", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".h",
    ".cs", ".go", ".rs", ".rb", ".php", ".sh", ".bat", ".ps1",
    ".sql", ".r", ".m", ".swift", ".kt", ".scala", ".lua",
    ".css", ".scss", ".less", ".log", ".env", ".gitignore",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}
PDF_EXTENSIONS = {".pdf"}
DOCX_EXTENSIONS = {".docx"}

ALL_READABLE = TEXT_EXTENSIONS | IMAGE_EXTENSIONS | PDF_EXTENSIONS | DOCX_EXTENSIONS


# ── public API ───────────────────────────────────────────

def file_type_label(path: Path) -> str:
    """Human-readable label for the file type (used by scanner)."""
    ext = path.suffix.lower()
    if ext in TEXT_EXTENSIONS:
        return "text"
    elif ext in PDF_EXTENSIONS:
        return "pdf"
    elif ext in IMAGE_EXTENSIONS:
        return "image"
    elif ext in DOCX_EXTENSIONS:
        return "docx"
    return "binary"


def is_extractable(path: Path) -> bool:
    """Can we extract text from this file?"""
    return path.suffix.lower() in ALL_READABLE


def extract_text(path: Path, max_chars: int = 200_000) -> Optional[str]:
    """
    Extract text from *path*, regardless of format.
    Used only by the indexer for semantic search.

    Returns:
        Extracted text string, or None if unsupported/failed.
    """
    ext = path.suffix.lower()

    try:
        if ext in TEXT_EXTENSIONS:
            return _read_text(path, max_chars)
        elif ext in PDF_EXTENSIONS:
            return _read_pdf(path, max_chars)
        elif ext in IMAGE_EXTENSIONS:
            return _read_image(path)
        elif ext in DOCX_EXTENSIONS:
            return _read_docx(path, max_chars)
        else:
            return None
    except Exception:
        return None


# ── plain text ───────────────────────────────────────────

def _read_text(path: Path, max_chars: int) -> Optional[str]:
    """Read a plain-text file with encoding fallbacks."""
    for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            text = path.read_text(encoding=encoding)[:max_chars]
            return text if text.strip() else None
        except (UnicodeDecodeError, ValueError):
            continue
        except (OSError, PermissionError):
            return None
    return None


# ── PDF via pymupdf ──────────────────────────────────────

def _read_pdf(path: Path, max_chars: int) -> Optional[str]:
    """Extract text from PDF using pymupdf."""
    try:
        import fitz  # pymupdf
    except ImportError:
        return None

    try:
        doc = fitz.open(str(path))
        pages = []
        for page in doc:
            pages.append(page.get_text())
        doc.close()
        text = "\n".join(pages)[:max_chars]
        return text if text.strip() else None
    except Exception:
        return None


# ── Images via EasyOCR ───────────────────────────────────

_ocr_reader = None


def _get_ocr_reader():
    """Lazy-load EasyOCR reader (uses GPU if available)."""
    global _ocr_reader
    if _ocr_reader is None:
        try:
            import easyocr
            import warnings
            warnings.filterwarnings("ignore", category=UserWarning)

            use_gpu = False
            try:
                import torch
                use_gpu = torch.cuda.is_available()
            except ImportError:
                pass

            _ocr_reader = easyocr.Reader(["en"], gpu=use_gpu, verbose=False)
        except ImportError:
            return None
        except Exception:
            return None
    return _ocr_reader


def _read_image(path: Path) -> Optional[str]:
    """Extract text from an image using EasyOCR."""
    try:
        ocr = _get_ocr_reader()
        if ocr is None:
            return None
        results = ocr.readtext(str(path), detail=0)
        text = "\n".join(results)
        return text if text.strip() else None
    except Exception:
        return None


# ── DOCX via python-docx ────────────────────────────────

def _read_docx(path: Path, max_chars: int) -> Optional[str]:
    """Extract text from a .docx file."""
    try:
        from docx import Document
    except ImportError:
        return None

    try:
        doc = Document(str(path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        text = "\n".join(paragraphs)[:max_chars]
        return text if text.strip() else None
    except Exception:
        return None
