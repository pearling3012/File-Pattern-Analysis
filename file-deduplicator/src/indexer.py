"""
indexer.py - Semantic search indexer using ChromaDB + Ollama.

Pipeline:
  1. Crawl directory for readable files
  2. Extract text from each file (reader.py)
  3. Chunk text into ~200 word segments
  4. Generate embeddings via Ollama (nomic-embed-text)
  5. Store chunks + metadata in ChromaDB (persisted to disk)

The ChromaDB database is stored in ./chroma_db/ alongside the project.
"""

import os
import hashlib
from pathlib import Path
from typing import Optional, Callable

import chromadb
import ollama as ollama_client

from . import crawler, reader


# ── config ───────────────────────────────────────────────

CHROMA_DIR = "chroma_db"
COLLECTION_NAME = "file_contents"
EMBED_MODEL = "nomic-embed-text"

CHUNK_WORDS = 200       # words per chunk (keep under model context limit)
CHUNK_OVERLAP = 40      # overlap between consecutive chunks
BATCH_SIZE = 10         # chunks per ChromaDB upsert batch
MAX_EMBED_CHARS = 2000  # max characters sent to Ollama (safe for nomic-embed-text 8192 tokens)


# ── Ollama embedding function for ChromaDB ───────────────

class OllamaEmbedder(chromadb.EmbeddingFunction):
    """Custom embedding function that calls Ollama locally."""

    def __init__(self, model: str = EMBED_MODEL):
        self.model = model

    def __call__(self, input: list[str]) -> list[list[float]]:
        embeddings = []
        for text in input:
            truncated = text[:MAX_EMBED_CHARS]
            try:
                resp = ollama_client.embed(model=self.model, input=truncated)
                embeddings.append(resp["embeddings"][0])
            except Exception:
                # If still too long, try with even shorter text
                try:
                    resp = ollama_client.embed(model=self.model, input=truncated[:500])
                    embeddings.append(resp["embeddings"][0])
                except Exception:
                    # Last resort: embed a placeholder
                    resp = ollama_client.embed(model=self.model, input="empty")
                    embeddings.append(resp["embeddings"][0])
        return embeddings


# ── text chunking ────────────────────────────────────────

def chunk_text(text: str, chunk_words: int = CHUNK_WORDS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    Split text into overlapping word-based chunks.

    Example: 1000 words with chunk_words=200, overlap=40 →
      chunk 1: words 0-199
      chunk 2: words 160-359
      chunk 3: words 320-519
      ...
    """
    words = text.split()
    if len(words) <= chunk_words:
        return [text] if words else []

    chunks = []
    start = 0
    step = chunk_words - overlap

    while start < len(words):
        end = start + chunk_words
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        if end >= len(words):
            break
        start += step

    return chunks


def _chunk_id(file_path: str, chunk_idx: int) -> str:
    """Deterministic ID for a chunk (so re-indexing overwrites, not duplicates)."""
    raw = f"{file_path}::chunk_{chunk_idx}"
    return hashlib.md5(raw.encode()).hexdigest()


# ── main indexing pipeline ───────────────────────────────

ProgressFn = Callable[[str, int, str], None]


def _ensure_ollama(model: str = EMBED_MODEL):
    """Check Ollama is running and the model is available."""
    try:
        ollama_client.show(model)
    except Exception:
        raise RuntimeError(
            f"Ollama model '{model}' not found.\n"
            f"  1. Install Ollama: https://ollama.com/download\n"
            f"  2. Pull the model: ollama pull {model}\n"
            f"  3. Make sure Ollama is running: ollama serve"
        )


def index_directory(
    root: Path,
    chroma_dir: str = CHROMA_DIR,
    progress: Optional[ProgressFn] = None,
) -> dict:
    """
    Index a directory for semantic search.

    Pipeline:
      1. Check Ollama is running
      2. Crawl files
      3. Extract text from each
      4. Chunk text
      5. Embed + store in ChromaDB

    Returns:
        Summary dict.
    """
    def _progress(phase: str, count: int, msg: str):
        if progress:
            progress(phase, count, msg)

    # ── Step 1: Check Ollama ─────────────────────────────
    _progress("check", 0, "Checking Ollama connection...")
    _ensure_ollama(EMBED_MODEL)
    _progress("check", 1, f"Ollama OK - model '{EMBED_MODEL}' ready.")

    # ── Step 2: Set up ChromaDB ──────────────────────────
    _progress("setup", 0, "Setting up ChromaDB...")
    embedder = OllamaEmbedder(model=EMBED_MODEL)
    client = chromadb.PersistentClient(path=chroma_dir)
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedder,
        metadata={"hnsw:space": "cosine"},
    )
    _progress("setup", 1, "ChromaDB ready.")

    # ── Step 3: Crawl + extract + chunk ──────────────────
    _progress("extract", 0, "Extracting text from files...")
    all_ids = []
    all_docs = []
    all_metas = []
    files_indexed = 0
    files_skipped = 0
    total_chunks = 0

    for info in crawler.crawl(root):
        if not reader.is_extractable(info.path):
            files_skipped += 1
            continue

        text = reader.extract_text(info.path)
        if not text or len(text.strip()) < 20:
            files_skipped += 1
            continue

        # Chunk the text
        chunks = chunk_text(text)
        if not chunks:
            files_skipped += 1
            continue

        file_path_str = str(info.path)
        ftype = reader.file_type_label(info.path)

        for i, chunk in enumerate(chunks):
            doc_id = _chunk_id(file_path_str, i)
            all_ids.append(doc_id)
            all_docs.append(chunk)
            all_metas.append({
                "path": file_path_str,
                "file_type": ftype,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "file_size": info.size,
                "file_name": info.path.name,
            })

        files_indexed += 1
        total_chunks += len(chunks)

        if files_indexed % 10 == 0:
            _progress("extract", files_indexed, f"Extracted {files_indexed} files ({total_chunks} chunks)...")

    _progress("extract", files_indexed, f"Extracted {files_indexed} files ({total_chunks} chunks).")

    if not all_ids:
        _progress("done", 0, "No extractable text found.")
        return {
            "files_indexed": 0,
            "files_skipped": files_skipped,
            "total_chunks": 0,
        }

    # ── Step 4: Embed + store in batches ─────────────────
    _progress("embed", 0, f"Embedding {total_chunks} chunks via Ollama...")

    for batch_start in range(0, len(all_ids), BATCH_SIZE):
        batch_end = batch_start + BATCH_SIZE
        batch_ids = all_ids[batch_start:batch_end]
        batch_docs = all_docs[batch_start:batch_end]
        batch_metas = all_metas[batch_start:batch_end]

        collection.upsert(
            ids=batch_ids,
            documents=batch_docs,
            metadatas=batch_metas,
        )

        done = min(batch_end, len(all_ids))
        _progress("embed", done, f"Embedded {done}/{total_chunks} chunks...")

    _progress("embed", total_chunks, f"Embedding done - {total_chunks} chunks stored.")

    return {
        "files_indexed": files_indexed,
        "files_skipped": files_skipped,
        "total_chunks": total_chunks,
    }


# ── search ───────────────────────────────────────────────

def search(
    query: str,
    n_results: int = 5,
    chroma_dir: str = CHROMA_DIR,
) -> list[dict]:
    """
    Semantic search across indexed files.

    Args:
        query:      Natural language question.
        n_results:  Number of results to return.
        chroma_dir: Path to ChromaDB storage.

    Returns:
        List of result dicts: {path, file_name, file_type, chunk_text, distance, score}
    """
    embedder = OllamaEmbedder(model=EMBED_MODEL)
    client = chromadb.PersistentClient(path=chroma_dir)

    try:
        collection = client.get_collection(
            name=COLLECTION_NAME,
            embedding_function=embedder,
        )
    except Exception:
        return []  # collection doesn't exist yet

    if collection.count() == 0:
        return []

    results = collection.query(
        query_texts=[query],
        n_results=min(n_results, collection.count()),
    )

    # Flatten ChromaDB's nested lists
    hits = []
    if results and results["ids"] and results["ids"][0]:
        for i in range(len(results["ids"][0])):
            meta = results["metadatas"][0][i]
            distance = results["distances"][0][i] if results["distances"] else 0
            # ChromaDB cosine distance: 0 = identical, 2 = opposite
            # Convert to similarity score: 1 - (distance/2)
            score = round((1 - distance / 2) * 100, 1)

            hits.append({
                "path": meta["path"],
                "file_name": meta["file_name"],
                "file_type": meta["file_type"],
                "chunk_index": meta["chunk_index"],
                "total_chunks": meta["total_chunks"],
                "chunk_text": results["documents"][0][i],
                "distance": distance,
                "score": score,
            })

    return hits
