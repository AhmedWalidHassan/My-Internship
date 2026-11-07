"""Ingestion pipeline: load -> chunk -> embed -> persist (incrementally).

* The FAISS index is saved to disk, so restarting the app does NOT re-embed.
* A manifest stores a content hash + chunk ids per file. On every `sync()` only
  new / changed files are embedded; deleted files are removed from the index.
* `add_file()` lets the UI add a single new document without a full rebuild.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

import settings


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_file(path: Path, name: str | None = None) -> list[Document]:
    """Split one file into chunks that carry source / category / section metadata."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".md":
        splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")],
            strip_headers=False,
        )
        sections = splitter.split_text(text)
    else:
        sections = [Document(page_content=text)]

    recursive = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE, chunk_overlap=settings.CHUNK_OVERLAP
    )
    chunks = recursive.split_documents(sections)

    name = name or path.name  # relative path inside the data folder, e.g. "hr/leave.md"
    category = settings.category_for(name)
    for i, chunk in enumerate(chunks):
        # Show h2/h3 when present (the h1 is just the file title); otherwise fall back to h1.
        parts = [v for k in ("h2", "h3") if (v := chunk.metadata.get(k))] or [chunk.metadata.get("h1") or path.stem]
        section = " > ".join(parts)
        chunk.metadata = {
            "source": name,
            "category": category,
            "section": section,
            "chunk": i,
        }
        # Prefixing source + section gives the embedding/BM25 useful context
        # (e.g. a bullet list that never mentions the topic by name).
        chunk.page_content = f"[{name} | {section}]\n{chunk.page_content}"
    return chunks


class IndexManager:
    def __init__(self, data_dir: Path | None = None, index_dir: Path | None = None, embeddings=None):
        self.data_dir = Path(data_dir or settings.DATA_DIR)
        self.index_dir = Path(index_dir or settings.INDEX_DIR)
        self.manifest_path = self.index_dir / "manifest.json"
        self.embeddings = embeddings or settings.get_embeddings()
        self.vectorstore: FAISS | None = None
        self.manifest: dict = {"fingerprint": settings.embedding_fingerprint(), "files": {}}

    # ----------------------------------------------------------------- helpers
    def _list_files(self) -> dict[str, Path]:
        return {
            p.relative_to(self.data_dir).as_posix(): p
            for p in sorted(self.data_dir.rglob("*"))
            if p.is_file() and p.suffix.lower() in settings.SUPPORTED_SUFFIXES
            and not any(part.startswith(".") for part in p.relative_to(self.data_dir).parts)
        }

    def _save(self) -> None:
        self.index_dir.mkdir(parents=True, exist_ok=True)
        if self.vectorstore is not None:
            self.vectorstore.save_local(str(self.index_dir))
        self.manifest_path.write_text(json.dumps(self.manifest, indent=2), encoding="utf-8")

    def _load_existing(self) -> bool:
        if not (self.manifest_path.exists() and (self.index_dir / "index.faiss").exists()):
            return False
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        if manifest.get("fingerprint") != settings.embedding_fingerprint():
            print("[ingestion] embedding/chunk settings changed -> rebuilding index")
            shutil.rmtree(self.index_dir, ignore_errors=True)
            return False
        self.vectorstore = FAISS.load_local(
            str(self.index_dir), self.embeddings, allow_dangerous_deserialization=True
        )  # safe: we wrote this file ourselves
        self.manifest = manifest
        return True

    def _add(self, name: str, path: Path, digest: str) -> int:
        chunks = chunk_file(path, name)
        ids = [f"{name}::{i}" for i in range(len(chunks))]
        if not chunks:
            return 0
        if self.vectorstore is None:
            self.vectorstore = FAISS.from_documents(chunks, self.embeddings, ids=ids)
        else:
            self.vectorstore.add_documents(chunks, ids=ids)
        self.manifest["files"][name] = {"hash": digest, "ids": ids}
        return len(chunks)

    def _remove(self, name: str) -> None:
        entry = self.manifest["files"].pop(name, None)
        if entry and self.vectorstore is not None:
            self.vectorstore.delete(entry["ids"])

    # ------------------------------------------------------------------ public
    def sync(self) -> dict:
        """Bring the persisted index in line with the data folder."""
        self._load_existing()
        files = self._list_files()
        report = {"added": [], "updated": [], "removed": [], "unchanged": []}

        for name in list(self.manifest["files"]):
            if name not in files:
                self._remove(name)
                report["removed"].append(name)

        for name, path in files.items():
            digest = _sha(path.read_text(encoding="utf-8"))
            known = self.manifest["files"].get(name)
            if known and known["hash"] == digest:
                report["unchanged"].append(name)
                continue
            if known:
                self._remove(name)
            self._add(name, path, digest)
            report["updated" if known else "added"].append(name)

        if self.vectorstore is None:
            raise RuntimeError(f"No documents found in {self.data_dir} (looked for {settings.SUPPORTED_SUFFIXES}).")
        if report["added"] or report["updated"] or report["removed"] or not self.manifest_path.exists():
            self._save()
        return report

    def add_file(self, filename: str, content: str) -> dict:
        """Save an uploaded document into the data folder and index just that file."""
        filename = Path(filename).name  # strip any path components
        if Path(filename).suffix.lower() not in settings.SUPPORTED_SUFFIXES:
            raise ValueError(f"Unsupported file type: {filename}")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / filename).write_text(content, encoding="utf-8")
        return self.sync()

    def stats(self) -> dict:
        n_chunks = sum(len(f["ids"]) for f in self.manifest["files"].values())
        return {"files": len(self.manifest["files"]), "chunks": n_chunks}


if __name__ == "__main__":
    mgr = IndexManager()
    print("data dir :", mgr.data_dir)
    print("sync     :", mgr.sync())
    print("stats    :", mgr.stats())
