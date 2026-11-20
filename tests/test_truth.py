"""
Fast tier — Week 3 Task 5: answer from the current, approved source.

Fixture documents (no index, no model): three versions of the PTO policy (v2.0 2025-01-01, v3.0
2026-03-01, a v4.0 draft), the 2024 handbook migrated to the legacy intranet, a wiki summary and a
meeting note. The fake generator answers from whichever passage the curation labelled CURRENT, so these
tests check what the generator is SHOWN, which is what `curate()` controls:

* time travel: AS_OF_DATE 2026-02-15 -> 5 days (v2.0 still current), default 2026-10-01 -> 3 days;
* a superseded version retrieved alone is replaced by the current one;
* a draft is labelled a proposal, never the rule; legacy copies on the same topic are dropped;
* the ambiguity policy: "the rover" with R2 and R3 documents -> answer both, never pick one;
* structured citations with version and section, and the cited versions for the log line.
"""

import re
from datetime import date

from conftest import FakeRetriever, prefix, scripted_llm
from langchain_core.documents import Document

from common.truth import Catalog, ambiguity_note, curate

PTO_V2 = Document(
    page_content="Paid Time Off Policy [HR-POL-004 v2.0 · Approved · effective 2025-01-01] › 3. Carry-over\n"
                 "Unused PTO of up to 5 days may be carried into the next calendar year.",
    id="v2::0", metadata={"source": "HR-POL-004_PTO_v2.pdf", "path": "policies/hr/HR-POL-004_PTO_v2.pdf",
                          "title": "Paid Time Off Policy", "doc_id": "HR-POL-004", "version": "2.0",
                          "status": "Approved", "effective_date": "2025-01-01", "section": "3. Carry-over",
                          "source_system": "policy-portal"})
PTO_V3 = Document(
    page_content="Paid Time Off Policy [HR-POL-004 v3.0 · Approved · effective 2026-03-01] › 3. Carry-over\n"
                 "Unused PTO of up to 3 days may be carried into the next calendar year and must be used by March 31.",
    id="v3::0", metadata={**PTO_V2.metadata, "source": "HR-POL-004_PTO_v3.pdf",
                          "path": "policies/hr/HR-POL-004_PTO_v3.pdf", "version": "3.0",
                          "effective_date": "2026-03-01"})
DRAFT = Document(
    page_content="DRAFT — Flexible Time Off (proposed HR-POL-004 v4.0) [HR-POL-004 v4.0 · DRAFT, not approved] › Proposal\n"
                 "Replace accrued PTO with Flexible Time Off: no fixed entitlement, minimum of 15 days.",
    id="v4::0", metadata={"source": "DRAFT_HR-POL-004_PTO_v4.md", "path": "policies/hr/DRAFT_HR-POL-004_PTO_v4.md",
                          "title": "DRAFT — Flexible Time Off", "doc_id": "HR-POL-004", "version": "4.0",
                          "status": "draft", "section": "Proposal", "source_system": "policy-portal"})
LEGACY = Document(
    page_content="Employee Handbook › 2. Paid Time Off (PTO)\nUnused PTO up to 5 days may be carried into the next "
                 "calendar year; anything above 5 days is forfeited on December 31.",
    id="hb::1", metadata={"source": "employee_handbook.md", "path": "legacy_intranet/employee_handbook.md",
                          "title": "Employee Handbook", "section": "2. Paid Time Off (PTO)",
                          "source_system": "intranet-legacy"})
WIKI = Document(
    page_content="Benefits Overview [2025-05-07]\nPTO: 20 days per year, up to 5 days carry over into the next year.",
    id="wiki::0", metadata={"source": "Benefits_Overview.html", "path": "wiki/people/Benefits_Overview.html",
                            "title": "Benefits Overview", "content_date": "2025-05-07", "source_system": "wiki"})
ALL = [PTO_V2, PTO_V3, DRAFT, LEGACY, WIKI]
CATALOG = Catalog(ALL)


def curator(as_of):
    def run(found, question):
        kept, notes = curate(found, question, CATALOG, as_of)
        return kept, notes, ambiguity_note(question, kept)
    return run


def answer_from_current(prompt: str) -> str:
    """A fake generator that does what the prompt asks: answer from the CURRENT passage."""
    m = re.search(r"\[([^\]|]+) \| (HR-POL-004 v([\d.]+)), effective (\S+): CURRENT[^\]]*\][^\n]*\n([^\n]+)",
                  prompt)
    if not m:
        return "I don't know based on the provided documents."
    days = re.search(r"up to (\d+) days", m.group(5)).group(1)
    return (f"Under HR-POL-004 v{m.group(3)}, effective {m.group(4)}, you can carry over up to {days} days.\n"
            f"Sources: {m.group(1)}")


def ask(app, docs, as_of, question="How many PTO days can I carry over?"):
    llm = scripted_llm(app)
    llm.rules[prefix(app.GENERATE_PROMPT)] = answer_from_current
    assistant = app.Assistant(FakeRetriever(docs), llm, curate=curator(as_of))
    return assistant.ask(question, "s"), llm


def test_time_travel_carry_over_is_5_days_before_march_2026_and_3_days_after(app):
    """The brief's time-travel test: as of 2026-02-15 v2.0 is current (v3.0 starts on 2026-03-01)."""
    before, llm_b = ask(app, [PTO_V2, PTO_V3, LEGACY], date(2026, 2, 15))
    after, llm_a = ask(app, [PTO_V2, PTO_V3, LEGACY], date(2026, 10, 1))      # the default AS_OF_DATE
    assert "up to 5 days" in before["answer"] and "HR-POL-004 v2.0" in before["answer"]
    assert "up to 3 days" in after["answer"] and "HR-POL-004 v3.0, effective 2026-03-01" in after["answer"]
    [gen_b] = llm_b.calls_to(prefix(app.GENERATE_PROMPT))
    assert "HR-POL-004 v3.0: NOT YET IN EFFECT on 2026-02-15 (takes effect 2026-03-01)" in gen_b
    [gen_a] = llm_a.calls_to(prefix(app.GENERATE_PROMPT))
    assert "up to 5 days may be carried" not in gen_a, "v2.0 (superseded) and the legacy copy are not shown"
    assert after["sources"] == [{"path": "policies/hr/HR-POL-004_PTO_v3.pdf", "title": "Paid Time Off Policy",
                                 "doc_id": "HR-POL-004", "version": "3.0", "effective_date": "2026-03-01",
                                 "section": "3. Carry-over", "status": "CURRENT"}]
    assert after["cited_versions"] == ["HR-POL-004 v3.0"]


def test_as_of_date_setting_defaults_to_the_corpus_snapshot():
    from common.settings import Settings
    assert Settings(_env_file=None).as_of_date == date(2026, 10, 1)
    assert Settings(_env_file=None, as_of_date="2026-02-15").as_of_date == date(2026, 2, 15)


def test_a_superseded_version_retrieved_alone_is_replaced_by_the_current_one():
    kept, notes = curate([PTO_V2, WIKI], "How many PTO days can I carry over?", CATALOG, date(2026, 10, 1))
    paths = [d.metadata["path"] for d in kept]
    assert "policies/hr/HR-POL-004_PTO_v3.pdf" in paths and "policies/hr/HR-POL-004_PTO_v2.pdf" not in paths
    assert any("added HR-POL-004 v3.0" in n for n in notes)
    assert paths[0].endswith("PTO_v3.pdf"), "the current policy comes first"


def test_a_draft_is_labelled_a_proposal_and_never_the_rule():
    kept, _ = curate([PTO_V3], "Is Northwind switching to flexible time off?", CATALOG, date(2026, 10, 1))
    draft = [d for d in kept if d.metadata["path"].endswith("DRAFT_HR-POL-004_PTO_v4.md")]
    assert draft, "the question uses the draft's terms, so the draft is shown, as a draft"
    assert draft[0].metadata["truth_status"] == "DRAFT"
    assert "NOT approved policy" in draft[0].metadata["truth_label"]
    assert kept[-1] is draft[0], "drafts come last, after every in-force source"


def test_legacy_copy_on_the_same_topic_is_dropped_and_wiki_is_flagged():
    kept, notes = curate([PTO_V3, LEGACY, WIKI], "How many PTO days can I carry over?", CATALOG, date(2026, 10, 1))
    statuses = {d.metadata["path"]: d.metadata["truth_status"] for d in kept}
    assert "legacy_intranet/employee_handbook.md" not in statuses
    assert statuses["wiki/people/Benefits_Overview.html"] == "LOWER_AUTHORITY"
    wiki = next(d for d in kept if d.metadata["path"].startswith("wiki/"))
    assert "HR-POL-004 applies" in wiki.metadata["truth_label"]


def test_ambiguity_policy_answers_every_reading_never_one_silently(app):
    """Policy (RESULTS.md Task 5): 'the rover' when the documents cover R2 and R3 -> answer for both."""
    r2 = Document(page_content="Warehouse Rover R2 - Data Sheet\nPayload capacity: 80 kg", id="r2::0",
                  metadata={"source": "r2.pdf", "path": "product/R2/r2.pdf", "title": "Warehouse Rover R2 - Data Sheet",
                            "source_system": "drive"})
    r3 = Document(page_content="Warehouse Rover R3 - Data Sheet\nPayload capacity: 120 kg", id="r3::0",
                  metadata={"source": "r3.pdf", "path": "product/R3/r3.pdf", "title": "Warehouse Rover R3 - Data Sheet",
                            "source_system": "drive"})
    llm = scripted_llm(app, answer="R2: 80 kg. R3: 120 kg.\nSources: r2.pdf, r3.pdf")
    assistant = app.Assistant(FakeRetriever([r2, r3]), llm, curate=curator(date(2026, 10, 1)))
    assistant.ask("What is the payload capacity of the rover?", "s1")
    [gen] = llm.calls_to(prefix(app.GENERATE_PROMPT))
    assert "Answer for BOTH, labelled 'R2:' and 'R3:'. Do not pick one." in gen
    assert ambiguity_note("What is the payload capacity of the R3?", [r2, r3]) is None
    assert "Never pick one silently" in app.GENERATE_PROMPT


def test_a_plain_folder_corpus_has_no_curation(app_backend):
    """The Week 1 corpus has no versions or source systems: the graph behaves exactly as in Week 2."""
    assert app_backend._curator() is None


def test_a_corpus_export_gets_a_curator(app, make_backend, temp_index_dir, tmp_path):
    from test_corpus_loading import mixed_export

    backend = make_backend(scripted_llm(app), data_dir=mixed_export(tmp_path / "corpus"))
    curator_fn = backend._curator()
    assert curator_fn is not None
    docs = list(backend.store.docstore._dict.values())
    kept, notes, ambiguity = curator_fn(docs, "How many PTO days carry over?")
    assert all("truth_status" in d.metadata for d in kept)


def test_the_grader_cannot_keep_a_wiki_page_and_drop_the_policy_it_contradicts():
    """'The sales IT tips say ...': a 4B grader kept the wiki page and dropped IT-STD-003 (live run)."""
    from common.truth import restore_anchors

    policy = Document(page_content="Password & Authentication Standard [IT-STD-003 v2.0 · Approved]\nCorporate "
                      "passwords must be at least 16 characters long. Passwords are no longer rotated on a schedule.",
                      metadata={"path": "policies/it/IT-STD-003.pdf", "doc_id": "IT-STD-003", "truth_status": "CURRENT"})
    tips = Document(page_content="IT tips for the sales team\nPasswords need at least 12 characters and must be "
                    "changed every 90 days. Use GlobalConnect on customer Wi-Fi.",
                    metadata={"path": "wiki/sales/Sales_IT_Tips.html", "truth_status": "LOWER_AUTHORITY"})
    unrelated = Document(page_content="Team: Security\nOffice hours Tuesday 14:00 for other teams.",
                         metadata={"path": "wiki/teams/Team_Security.html", "truth_status": "LOWER_AUTHORITY"})
    kept, notes = restore_anchors([tips], [policy, tips])
    assert kept[0] is policy and notes, "the policy comes back, first"
    kept, notes = restore_anchors([unrelated], [policy, unrelated])
    assert kept == [unrelated] and not notes, "an unrelated page doesn't pull a policy in"


def test_cited_versions_name_each_version_once_in_citation_order():
    from common.truth import cited_versions
    v3 = {"path": "policies/hr/HR-POL-004_PTO_v3.pdf", "doc_id": "HR-POL-004", "version": "3.0"}
    wiki = {"path": "wiki/people/Benefits_Overview.html", "doc_id": None, "version": None}
    assert cited_versions([dict(v3, section="2. Accrual"), wiki, dict(v3, section="3. Carry-over")]) == \
        ["HR-POL-004 v3.0", "wiki/people/Benefits_Overview.html"]
