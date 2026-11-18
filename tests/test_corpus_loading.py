"""
Week 3 Task 2 — the loader reads a corpus EXPORT (a folder with `_metadata.csv`): the documents
listed there, in sub-folders, keyed by their corpus path. What it can't parse yet is skipped
LOUDLY (one warning with the count per format), never silently: the Week 3 Task 1 finding was
that the Week 2 loader indexed 1 of 191 files and logged success.
"""

import logging


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


def test_export_is_indexed_from_metadata_and_every_skip_is_logged(app, temp_index_dir, tmp_path, fake_embeddings, caplog):
    corpus = write_export(tmp_path / "corpus")
    files, skipped = app.corpus_files(corpus)
    assert list(files) == ["meetings/2026-01-01_team.txt", "policies/hr/DRAFT_pto.md"]
    assert "README.md" not in files and not any(k.endswith(".csv") for k in files)
    assert skipped == {".pdf": 1, "listed but missing": 1}

    with caplog.at_level(logging.WARNING, logger="northwind"):
        app.log.propagate = True                       # let caplog see the app's logger
        try:
            store, stats = app.ingest(fake_embeddings, corpus)
        finally:
            app.log.propagate = False
    assert stats["skipped"] == {".pdf": 1, "listed but missing": 1}
    warning = " ".join(r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)
    assert "SKIPPED 2" in warning and ".pdf 1" in warning, warning
    docs = list(store.docstore._dict.values())
    assert {d.metadata["path"] for d in docs} == set(files)
    assert {d.metadata["source"] for d in docs} == {"2026-01-01_team.txt", "DRAFT_pto.md"}
    assert all(i.split("::")[0] in files for i in store.docstore._dict)


def test_a_plain_folder_keeps_the_week2_behaviour(app, corpus_dir):
    files, skipped = app.corpus_files(corpus_dir)
    assert list(files) == ["handbook.md", "it_faq.md"] and skipped == {}
