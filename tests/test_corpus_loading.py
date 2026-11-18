"""
Week 3 Task 2 — the loader reads a corpus EXPORT (a folder with `_metadata.csv`): the documents
listed there, in sub-folders, keyed by their corpus path. What it can't parse yet is skipped
LOUDLY (one warning with the count per format), never silently: the Week 3 Task 1 finding was
that the Week 2 loader indexed 1 of 191 files and logged success.
"""

import logging

from langchain_core.embeddings import DeterministicFakeEmbedding, Embeddings


def write_export(root):
    (root / "policies" / "hr").mkdir(parents=True)
    (root / "meetings").mkdir()
    (root / "README.md").write_text("# Export note\nNot a document.\n", encoding="utf-8")
    (root / "_directory.csv").write_text("user_id,name\nu1,A\n", encoding="utf-8")
    (root / "policies" / "hr" / "DRAFT_pto.md").write_text("# Draft\n\n## Proposal\nFlexible time off, minimum 15 days.\n",
                                                           encoding="utf-8")
    (root / "policies" / "hr" / "HR-POL-005_sick_leave.pdf").write_bytes(b"%PDF-1.4 not parsed yet")
    (root / "meetings" / "2026-01-01_team.txt").write_text("Team sync\nNotes: Karim is on PTO next week.\n",
                                                          encoding="utf-8")
    (root / "_metadata.csv").write_text(
        "path,title,owner_team,acl_groups,last_modified,source_system\n"
        "policies/hr/DRAFT_pto.md,Draft,People,all,2026-09-18,policy-portal\n"
        "policies/hr/HR-POL-005_sick_leave.pdf,Sick leave,People,all,2025-01-01,policy-portal\n"
        "meetings/2026-01-01_team.txt,Team sync,Eng,all,2026-01-01,drive\n"
        "wiki/gone.html,Gone,IT,all,2025-01-01,wiki\n", encoding="utf-8")
    return root


def test_export_is_indexed_from_metadata_and_every_skip_is_listed(app, temp_index_dir, tmp_path, fake_embeddings,
                                                                  caplog, capsys):
    """Week 3 Task 3: every listed document is attempted with its format's loader. One that can't
    be (missing, or a corrupt PDF) is skipped WITH its reason: in stats, in the warning, in
    ingestion_report.json and as a structured JSON log line. Never silently."""
    import json

    corpus = write_export(tmp_path / "corpus")
    files, skipped = app.corpus_files(corpus)
    assert list(files) == ["meetings/2026-01-01_team.txt", "policies/hr/DRAFT_pto.md",
                           "policies/hr/HR-POL-005_sick_leave.pdf"]
    assert "README.md" not in files and not any(k.endswith(".csv") for k in files)
    assert skipped == {"wiki/gone.html": "listed in _metadata.csv but missing"}

    with caplog.at_level(logging.WARNING, logger="northwind"):
        app.log.propagate = True                       # let caplog see the app's logger
        try:
            store, stats = app.ingest(fake_embeddings, corpus)
        finally:
            app.log.propagate = False
    assert set(stats["skipped"]) == {"wiki/gone.html", "policies/hr/HR-POL-005_sick_leave.pdf"}
    assert stats["skipped"]["policies/hr/HR-POL-005_sick_leave.pdf"].startswith("could not be parsed")
    warning = " ".join(r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)
    assert "2 listed documents SKIPPED" in warning and "HR-POL-005_sick_leave.pdf" in warning, warning

    report = json.loads((temp_index_dir / "ingestion_report.json").read_text(encoding="utf-8"))
    assert report["documents_loaded"] == 2 and report["documents_skipped"] == 2
    assert {d["path"] for d in report["documents"] if d["status"] == "skipped"} == set(stats["skipped"])
    lines = [json.loads(x) for x in capsys.readouterr().out.splitlines() if x.startswith("{")]
    assert [x["event"] for x in lines].count("ingest_document_skipped") == 2
    run = next(x for x in lines if x["event"] == "ingest")
    assert run["documents_loaded"] == 2 and run["embedding_calls"] == stats["embedded_chunks"] and "ts" in run

    docs = list(store.docstore._dict.values())
    assert {d.metadata["path"] for d in docs} == {"meetings/2026-01-01_team.txt", "policies/hr/DRAFT_pto.md"}
    assert {d.metadata["source"] for d in docs} == {"2026-01-01_team.txt", "DRAFT_pto.md"}
    draft = next(d for d in docs if d.metadata["path"].endswith("DRAFT_pto.md"))
    assert draft.metadata["acl_groups"] == "all" and draft.metadata["source_system"] == "policy-portal"


def test_a_plain_folder_keeps_the_week2_behaviour(app, corpus_dir):
    files, skipped = app.corpus_files(corpus_dir)
    assert list(files) == ["handbook.md", "it_faq.md"] and skipped == {}


class CountingEmbeddings(Embeddings):
    """Deterministic offline embeddings that record every text they embed."""

    def __init__(self):
        self.inner = DeterministicFakeEmbedding(size=32)
        self.embedded: list[str] = []

    def embed_documents(self, texts):
        self.embedded.extend(texts)
        return self.inner.embed_documents(texts)

    def embed_query(self, text):
        return self.inner.embed_query(text)


def mixed_export(root):
    """A small export in three formats, with the sub-folders and _metadata.csv of the real one."""
    (root / "policies").mkdir(parents=True)
    (root / "wiki").mkdir()
    (root / "cairo").mkdir()
    (root / "policies" / "pto.md").write_text(
        "# PTO policy\n\n## Carry-over\nUp to 3 days carry over and must be used by March 31.\n\n"
        "## Requests\nAsk 5 business days ahead.\n", encoding="utf-8")
    (root / "wiki" / "VPN.html").write_text(
        "<html><body><div class='nav'>Home &gt; IT</div><div class='content'><h1>VPN</h1>"
        "<p>Install Northwind Access from Self-Service.</p></div>"
        "<div class='footer'>Last edited by it on 2026-07-01. Was this page helpful?</div></body></html>",
        encoding="utf-8")
    (root / "cairo" / "holidays.csv").write_text("﻿المناسبة,التاريخ\nعيد الفطر,2026-03-20\nشم النسيم,2026-04-13\n",
                                                 encoding="utf-8")
    (root / "_metadata.csv").write_text(
        "path,title,owner_team,acl_groups,last_modified,source_system\n"
        "policies/pto.md,PTO,People,all,2026-03-01,policy-portal\n"
        "wiki/VPN.html,VPN,IT,all,2026-07-01,wiki\n"
        "cairo/holidays.csv,Holidays,People,all,2025-12-20,wiki\n", encoding="utf-8")
    return root


def test_changing_one_document_reembeds_only_it_and_invalidates_cached_answers(app, start_api, make_backend,
                                                                                 temp_index_dir, tmp_path):
    """Week 3 Task 3: content hashes per document. Editing ONE file of the export re-embeds only that
    file's chunks (counted), and the answers cached before the edit are no longer served. Removing a
    file embeds nothing, deletes its vectors and invalidates too."""
    import uuid

    from conftest import scripted_llm

    corpus = mixed_export(tmp_path / "corpus")
    emb = CountingEmbeddings()
    backend = make_backend(scripted_llm(app), data_dir=corpus, embeddings=emb)
    first = len(emb.embedded)
    assert first == backend.n_chunks and backend.ingest_stats["documents"] == 3
    client = start_api(lambda: backend)

    def ask():
        r = client.post("/chat", json={"question": "How many PTO days carry over?", "session_id": str(uuid.uuid4())})
        assert r.status_code == 200, r.text
        return r.json()

    ready = client.get("/readyz").json()
    assert ready["documents"] == 3 and ready["documents_skipped"] == 0 and ready["corpus_snapshot"] == "2026-07-01"   # no cover note: newest last_modified
    assert ready["index_built_at"] and ready["index_build_seconds"] is not None
    ask()
    assert ask()["cache_hit"] is True

    pto = corpus / "policies" / "pto.md"
    pto.write_text(pto.read_text(encoding="utf-8").replace("Up to 3 days", "Up to 4 days"), encoding="utf-8")
    before = len(emb.embedded)
    backend.refresh()
    new = emb.embedded[before:]
    pto_chunks = [d for d in backend.store.docstore._dict.values() if d.metadata["path"] == "policies/pto.md"]
    assert backend.ingest_stats["updated"] == ["policies/pto.md"] and backend.ingest_stats["reused"] == [
        "cairo/holidays.csv", "wiki/VPN.html"]
    assert len(new) == len(pto_chunks) == backend.ingest_stats["embedded_chunks"] > 0
    assert all("PTO policy" in t for t in new), "only the changed document's chunks were embedded"
    assert ask()["cache_hit"] is False, "an answer cached before the edit must not be served"

    (corpus / "wiki" / "VPN.html").unlink()
    before = len(emb.embedded)
    backend.refresh()
    assert len(emb.embedded) == before, "removing a document embeds nothing"
    assert backend.ingest_stats["removed"] == ["wiki/VPN.html"]
    assert "wiki/VPN.html" not in {d.metadata["path"] for d in backend.store.docstore._dict.values()}
    assert ask()["cache_hit"] is False
