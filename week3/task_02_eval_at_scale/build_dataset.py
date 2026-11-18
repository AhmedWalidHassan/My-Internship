"""
Task 2 — build the 100-example Week 3 eval set (dataset v3) and its dev/test split.

    python week3/task_02_eval_at_scale/build_dataset.py
        -> week3/eval/eval_v3.jsonl            (100 examples, `split` = dev | test)
        -> week3/task_02_eval_at_scale/dataset_report.md   (where every example came from)

Three sources, in this order:

1. **Week 2 (38 examples, week2/task_07_eval_gate/eval_dataset.jsonl).** Migrated to the Week 3
   schema with their original IDs. The Task 1 verdicts (week3/task_01_meet_the_corpus/
   w2_eval_triage.jsonl) are applied: "world changed" examples get the new truth and the policy
   document that states it. gold_docs list the AUTHORITATIVE document, as the seed set does (s01's
   gold is HR-POL-005, not the legacy handbook that also says "10 days").
2. **The seed set (40).** Merged. The 10 that duplicate a Week 2 example are dropped (Week 2's
   version kept, overlap noted in the report).
3. **New (32)** for the categories still short of 5. Hand-written where the category is a design
   decision (conflict, draft, ambiguous, personalized, access), LLM-generated and reviewed where it
   is "a fact in a passage" (synth/candidates_reviewed.jsonl: 65 generated, 10 accepted).

The split is stratified by category (access also by direction: refused vs answered), ~30% test,
with a fixed seed. Once committed, TEST IS FROZEN: rebuilding with different content must bump
the dataset version and say so.
"""

from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
W2 = REPO / "week2" / "task_07_eval_gate" / "eval_dataset.jsonl"
TRIAGE = REPO / "week3" / "task_01_meet_the_corpus" / "w2_eval_triage.jsonl"
SEED = REPO / "week3" / "eval" / "seed_eval.jsonl"
OUT = REPO / "week3" / "eval" / "eval_v3.jsonl"
REPORT = Path(__file__).resolve().parent / "dataset_report.md"
REFUSAL = "I don't know based on the provided documents."
CATEGORIES = ("factual", "table", "keyword", "version", "conflict", "draft", "multi_hop", "multi_part",
              "ambiguous", "long_doc", "cross_lingual", "follow_up", "personalized", "access", "out_of_scope")

P, F, I = "policies/hr/", "policies/finance/", "policies/it/"
R2, R3 = "product/R2/Warehouse_Rover_R2_datasheet.pdf", "product/R3/Warehouse_Rover_R3_datasheet.pdf"
PTO3, SLA = P + "HR-POL-004_PTO_v3.pdf", "product/Support_SLA_2026.pdf"
TRAVEL, PARTS = F + "FIN-POL-002_travel_and_per_diem.pdf", "product/Spare_Parts_Catalog_2026.pdf"
DRAFT, MANUAL = P + "DRAFT_HR-POL-004_PTO_v4_flexible_time_off.md", "product/R3/R3_Operator_Manual_RevC.pdf"
CAIRO_GUIDE, RAMADAN = "cairo/دليل_مكتب_القاهرة.md", "cairo/ساعات_العمل_في_رمضان.md"

# --- 1. Week 2 migration: id -> (W3 category, user_id, gold_docs, must_include, reference or None = W2's,
#        question or None = W2's). The W2 category map from the brief, adjusted where the question now
#        tests a Week 3 behaviour (noted in the report).
W2_MAP = {
    1: ("personalized", "u1002", [PTO3], ["20"],
        "20 days. PTO now depends on completed years of service on January 1; hired 2024-09-01, you had 1 "
        "completed year on 2026-01-01, which is the 0-2 year band (20 days).", None),
    2: ("version", "u1001", [PTO3], ["3 days|three days|up to 3", "March 31"], None, None),
    3: ("version", "u1001", [PTO3], ["60"], None, None),
    4: ("factual", "u1001", [PTO3], ["5 business days|five business days"], None, None),
    5: ("factual", "u1001", [P + "HR-POL-005_sick_leave.pdf"], ["10"], None, None),
    6: ("factual", "u1001", [P + "HR-POL-005_sick_leave.pdf"], ["3 consecutive|three consecutive"], None, None),
    7: ("factual", "u1001", [P + "HR-POL-010_remote_work.pdf"], ["3 days|three days"], None, None),
    8: ("version", "u1001", [P + "HR-POL-010_remote_work.pdf"], ["600"], None, None),
    9: ("version", "u1001", [P + "HR-POL-006_parental_leave.pdf"], ["12 weeks|twelve weeks"], None, None),
    10: ("table", "u1001", [TRAVEL], ["90", "55", "70"], None, None),
    11: ("factual", "u1001", [TRAVEL], ["not reimbursable|not be reimbursed|isn't reimbursable|is not covered"], None, None),
    12: ("factual", "u1001", [F + "FIN-POL-001_expense_reimbursement.pdf"], ["30 days"],
         "Within 30 days of the expense, via the Finance portal with itemised receipts over $25; expenses "
         "submitted more than 90 days later are not reimbursed.", None),
    13: ("multi_part", "u1001", [P + "HR-POL-014_referral_bonus.pdf"], ["4,000|4000", "3,000|3000", "90 days", "12 months"], None, None),
    14: ("factual", "u1001", [P + "HR-POL-020_performance_reviews.pdf"], ["June", "December"], None, None),
    15: ("version", "u1001", [P + "HR-POL-016_learning_development.pdf"], ["2,000|2000"], None, None),
    16: ("multi_part", "u1001", [I + "IT-STD-009_lost_or_stolen_devices.pdf"], ["1 hour|one hour|within an hour", "wipe"], None, None),
    17: ("multi_part", "u1001", [I + "IT-STD-003_password_and_authentication.pdf"],
         ["16", "MFA|multi-factor", "rotat|changed immediately|change it immediately|compromise"], None, None),
    18: ("conflict", "u1001", [I + "IT-STD-007_remote_access.pdf"], ["Northwind Access"], None, None),
    19: ("factual", "u1001", [I + "IT-STD-007_remote_access.pdf"], ["email"],
         "No. Personal devices may only access email and calendar, through the browser, and cannot run "
         "Northwind Access, so they can't reach source code.", None),
    20: ("factual", "u1001", ["legacy_intranet/it_faq.md"], ["50"], None, None),
    21: ("factual", "u1001", [R2], ["80 kg|80kg"], None, None),
    22: ("ambiguous", "u1001", [R2, R3], ["1.8", "2.0|2 m/s"],
         "It depends on the rover: the R2 does 1.8 m/s loaded (2.2 unloaded), the R3 2.0 m/s loaded (2.5 unloaded).", None),
    23: ("multi_part", "u1001", [SLA], ["24/7", "1 hour|1-hour|one hour", "48 hours|48-hour"],
         "24/7 coverage, a 1-hour first response (Severity 1) and critical parts within 48 hours.", None),
    24: ("factual", "u1001", [R2], ["IP54|indoor"], None, None),
    25: ("out_of_scope", "u1001", [], [], None, None),
    26: ("out_of_scope", "u1001", [], [], None, None),
    27: ("out_of_scope", "u1001", [], [], None, None),
    28: ("out_of_scope", "u1001", [], [], None, None),
    29: ("multi_hop", "u1001", [P + "HR-POL-014_referral_bonus.pdf", PTO3], ["90 days", "12 months", "60"], None, None),
    30: ("multi_hop", "u1001", [P + "HR-POL-010_remote_work.pdf", I + "IT-STD-007_remote_access.pdf"],
         ["director", "Northwind Access"], None, None),
    31: ("multi_part", "u1001", [R2, "legacy_intranet/product_specs.md"], ["outdoor|indoor|IP54", "3 cm"],
         "Indoor use only (IP54, not for outdoor or wet environments), not recommended on floors with gaps "
         "wider than 3 cm; reflective or glass surfaces degrade LiDAR; ramps up to 5 degrees.", None),
    32: ("multi_part", "u1001", [TRAVEL], ["Navan", "6 hours", "CFO"], None, None),
    33: ("out_of_scope", "u1001", [], [], None, None),
    34: ("out_of_scope", "u1001", [], [], None, None),
    35: ("follow_up", "u1001", [P + "HR-POL-005_sick_leave.pdf"],
         ["not carry|doesn't carry|does not carry|don't carry|do not carry|cannot be carried|can't be carried"], None, None),
    36: ("follow_up", "u1001", [SLA], ["4 hours|4-hour|four hours"],
         "Business hours Monday to Friday, 09:00-17:00 customer local time, 4-hour first response and critical "
         "parts in 5 business days.", None),
    37: ("keyword", "u1001", ["product/fleet_manager/release_notes_4.3.md"], ["one-way|missions/bulk|dock queue"],
         "Battery-aware scheduling that considers dock queue length, one-way aisle traffic rules, and "
         "/missions/bulk in REST API v1; it is the last 4.x feature release (max 50 rovers).",
         "What did Fleet Manager 4.3 add?"),
    38: ("keyword", "u1001", [R2], ["optional"], None, None),
}

# Seed examples that duplicate a Week 2 example: keep Week 2's (brief), note the overlap.
SEED_DUPLICATES = {"s01": 5, "s02": 2, "s03": 9, "s05": 18, "s13": 17, "s14": 13, "s16": 26,
                   "s30": 15, "s31": 8, "s39": 10}


def ex(id, category, user, question, reference, gold, must, must_not=(), refusal=False, history=(), origin=""):
    return {"id": id, "category": category, "user_id": user, "history": list(history), "question": question,
            "reference_answer": reference, "gold_docs": list(gold), "must_include": list(must),
            "must_not_include": list(must_not), "expect_refusal": refusal, "origin": origin}


H, S = "new (hand-written)", "new (LLM-generated {}, reviewed{})"
NEW = [
    ex("n01", "table", "u1001", "What is the hotel cap per night for a business trip to India?",
       "$150 per night: India is a Tier B destination.", [TRAVEL], ["150"], origin=H),
    ex("n02", "table", "u1001", "How much does the 5G connectivity module cost?",
       "$310 (part NW-5G-0003; optional on the R2, included on the R3).", [PARTS], ["310"], origin=S.format("c009", "")),
    ex("n03", "table", "u1001", "How quickly do Premium Plus customers receive critical spare parts?",
       "Within 24 hours (plus an on-site technician within 24 hours in supported metro areas).", [SLA, PARTS],
       ["24 hours|24-hour"], origin=S.format("c007", "")),
    ex("n04", "keyword", "u1001", "How do I fix error E-301?",
       "E-301 means the Fleet Manager certificate expired: renew the site certificate in Fleet Manager > Settings > Security.",
       ["product/Rover_Error_Codes_2026.xlsx"], ["certificate"], origin=S.format("c045", "")),
    ex("n05", "conflict", "u1003", "I lost my laptop at a trade show. Is it OK to email IT the next morning?",
       "No. Report it to Security (security@northwind.example) within 1 hour of noticing and file an URGENT IT ticket; "
       "the sales IT tips page that says 'the next morning' is out of date.",
       [I + "IT-STD-009_lost_or_stolen_devices.pdf"], ["1 hour|one hour|within an hour"], origin=H),
    ex("n06", "conflict", "u1003", "The sales IT tips say passwords need 12 characters and must be changed every 90 days. Is that right?",
       "No. IT-STD-003 v2.0 requires at least 16 characters and no scheduled rotation (change it only if compromise is suspected).",
       [I + "IT-STD-003_password_and_authentication.pdf"], ["16"], origin=H),
    ex("n07", "conflict", "u1002", "How many days a week can I work remotely during Ramadan?",
       "In the Cairo office, up to 4 days a week during Ramadan with your direct manager's approval (the company-wide default is 3).",
       [RAMADAN, P + "HR-POL-010_remote_work.pdf"], ["4|four"], origin=S.format("c053", ", re-categorised as conflict")),
    ex("n08", "draft", "u1001", "Is Northwind switching to flexible time off?",
       "Not currently. Flexible Time Off is a DRAFT proposal (proposed HR-POL-004 v4.0), not approved; the current policy is "
       "HR-POL-004 v3.0. The proposal's effective date would be 2027-01-01, subject to leadership approval.",
       [DRAFT, PTO3], ["draft|not approved|proposal|proposed"], origin=H),
    ex("n09", "draft", "u1001", "What is the minimum amount of time off I must take under the flexible time off policy?",
       "Flexible time off is only a draft proposal, not policy. The draft proposes a minimum of 15 days a year.",
       [DRAFT], ["draft|not approved|proposal|proposed", "15"], origin=H),
    ex("n10", "draft", "u1001", "By when can I send comments on the flexible time off proposal?",
       "By October 31, 2026, to people-ops@northwind.example (it is a draft for comment, not approved).",
       [DRAFT], ["October 31|2026-10-31|31 October|Oct 31"], origin=H),
    ex("n11", "draft", "u1001", "Has PTO carry-over been abolished?",
       "No. Under HR-POL-004 v3.0 up to 3 days carry over and must be used by March 31. The flexible time off draft (no "
       "balance to carry over) is not approved.", [PTO3, DRAFT], ["3 days|three days|up to 3"], origin=H),
    ex("n12", "long_doc", "u1001", "How should I prepare an R3 for storage of more than a month?",
       "Charge the battery to between 50% and 60% first, and top it up every 3 months.", [MANUAL],
       ["50", "60", "3 months|three months"], origin=S.format("c023", ", merged with c024")),
    ex("n13", "long_doc", "u1001", "How high a threshold can the R3 cross?",
       "Thresholds up to 2 cm high (and floor gaps up to 4 cm wide), at reduced speed.", [MANUAL], ["2 cm"],
       origin=S.format("c026", "")),
    ex("n14", "long_doc", "u1001", "Can the R3 work on an outdoor loading dock in hot weather?",
       "Only under cover, in at most light rain, and at 0 to 40 degrees Celsius; suspend outdoor missions when standing water is present.",
       [MANUAL], ["40"], origin=H),
    ex("n15", "cross_lingual", "u1002", "What are the Cairo office's opening hours?",
       "Sunday to Thursday, 8:00 am to 7:00 pm.", [CAIRO_GUIDE],
       ["8:00|8 am|8am|08:00|8 a.m", "7:00|7 pm|7pm|19:00|7 p.m"], origin=S.format("c050", "")),
    ex("n16", "cross_lingual", "u1002", "How much does it cost to replace a lost access badge at the Cairo office?",
       "200 Egyptian pounds, at reception.", [CAIRO_GUIDE], ["200"], origin=S.format("c051", "")),
    ex("n17", "cross_lingual", "u1002", "How many days off is Eid al-Fitr in 2026 for the Cairo office?",
       "3 days, from March 20, 2026.", ["cairo/الإجازات_الرسمية_2026.csv"], ["3 days|three days|3-day|three-day"],
       origin=S.format("c055", "")),
    ex("n18", "multi_hop", "u1001", "We only run Fleet Manager 4.3. Can we add an R3 to our fleet?",
       "Not on 4.3: the R3 requires Fleet Manager 5.0 or later and isn't supported by 4.x. You would need a 5.x instance "
       "(and R2 units can't move to 5.x).", [R3, "product/fleet_manager/release_notes_5.0.md"], ["5.0|5.x"], origin=H),
    ex("n19", "ambiguous", "u1001", "How long is parental leave?",
       "Birth parents get 16 weeks of fully paid leave; non-birth and adoptive parents get 12 weeks.",
       [P + "HR-POL-006_parental_leave.pdf"], ["16", "12"], origin=H),
    ex("n20", "ambiguous", "u1001", "Which battery pack does the rover use?",
       "R2: NW-BAT-4380 (48V 30Ah); R3: NW-BAT-4830 (48V 40Ah). They are not interchangeable.", [PARTS, R2, R3],
       ["4380", "4830"], origin=H),
    ex("n21", "ambiguous", "u1001", "Which Fleet Manager version do I need for the rover?",
       "R2: Fleet Manager 4.x (4.3; R2 is not supported on 5.x). R3: Fleet Manager 5.0 or later.",
       [R3, "product/R2/R2_End_of_Life_Notice.md"], ["4.3|4.x", "5.0|5.x"], origin=H),
    ex("n22", "follow_up", "u1001", "And how fast does it go when it's loaded?", "2.0 m/s loaded (2.5 m/s unloaded).",
       [R3], ["2.0|2 m/s"], history=[{"role": "user", "content": "What's the payload capacity of the R3?"},
                                     {"role": "assistant", "content": "The Warehouse Rover R3 carries up to 120 kg."}], origin=H),
    ex("n23", "multi_hop", "u1001", "My rover has shown E-217 three times today. Which part should be replaced, and what does it cost?",
       "Replace the drive motor controller NW-MC-2210 (E-217 recurring 3 times in 24 hours); list price $640.",
       ["product/Rover_Error_Codes_2026.xlsx", PARTS], ["NW-MC-2210", "640"], origin=H),
    ex("n24", "personalized", "u3001", "How many PTO days do I get this year?",
       "23 days: hired 2020-01-06, you had 5 completed years of service on January 1, 2026 (3-5 year band).",
       [PTO3], ["23"], origin=H),
    ex("n25", "personalized", "u1003", "How much annual PTO am I entitled to?",
       "25 days: hired 2019-02-18, you had 6 completed years of service on January 1, 2026 (6+ years).",
       [PTO3], ["25"], origin=H),
    ex("n26", "personalized", "u1001", "Do I get the monthly transport allowance?",
       "No: the monthly transport allowance (EGP 1,500) is for full-time employees of the Cairo office; you are in Austin.",
       ["cairo/بدل_الانتقالات.md"], ["Cairo"], origin=H),
    ex("n27", "personalized", "u1001", "Is January 19 a company holiday for me?",
       "Yes: January 19 (Martin Luther King Jr. Day) is an Austin office holiday in 2026.",
       ["wiki/people/US_Holidays_2026.html"], ["yes|MLK|Martin Luther King"], origin=S.format("c056", ", rewritten as personalized")),
    ex("n28", "access", "u1002", "What is the merit budget for the 2026 compensation review?", REFUSAL, [], [],
       ["3.5%"], refusal=True, origin=H),
    ex("n29", "access", "u3002", "When will employees affected by Project Juniper be informed?",
       "On November 12, 2026.", ["hr_restricted/Project_Juniper_Workforce_Plan.md"],
       ["November 12|Nov 12|12 November|2026-11-12"], origin=H),
    ex("n30", "access", "u3001", "What is Project Juniper?", REFUSAL, [], [], ["18 roles", "November 12"],
       refusal=True, origin=H),
    ex("n31", "access", "u1003", "What target rating distribution should managers use in calibration?", REFUSAL, [], [],
       ["70%"], refusal=True, origin=H),
    ex("n32", "access", "u2001", "How long is a performance improvement plan?",
       "60 days, agreed with People Operations before it is shared with the employee.",
       ["hr_restricted/Disciplinary_Procedure.pdf"], ["60"], origin=H),
]


def migrate_w2() -> list[dict]:
    triage = {t["id"]: t for t in map(json.loads, open(TRIAGE, encoding="utf-8"))}
    out = []
    for e in map(json.loads, open(W2, encoding="utf-8")):
        cat, user, gold, must, ref, question = W2_MAP[e["id"]]
        t = triage[e["id"]]
        refusal = e["expect_refusal"]
        reference = ref or t["new_reference"] or (REFUSAL if refusal else e["reference"])
        history = [m for u, a in e["history"] for m in ({"role": "user", "content": u},
                                                       {"role": "assistant", "content": a})]
        out.append(ex(str(e["id"]), cat, user, question or e["question"], reference, gold, must, refusal=refusal,
                      history=history, origin=f"week2 #{e['id']} ({e['category']}; Task 1 verdict: {t['status']})"))
    return out


def merge_seed() -> tuple[list[dict], list[str]]:
    kept, notes = [], []
    for e in map(json.loads, open(SEED, encoding="utf-8")):
        if e["id"] in SEED_DUPLICATES:
            notes.append(f"{e['id']} ({e['category']}) duplicates Week 2 #{SEED_DUPLICATES[e['id']]}: kept #{SEED_DUPLICATES[e['id']]}")
            continue
        kept.append({**e, "origin": "seed"})
    return kept, notes


def split(examples: list[dict], test_share=0.3, seed=7) -> None:
    """Stratified: every category in both splits; access also by direction (refuse / answer)."""
    rng = random.Random(seed)
    groups = defaultdict(list)
    for e in examples:
        key = (e["category"], e["expect_refusal"]) if e["category"] == "access" else (e["category"],)
        groups[key].append(e)
    quota = {k: test_share * len(v) for k, v in groups.items()}
    n_test = round(test_share * len(examples))
    take = {k: max(1, int(q)) for k, q in quota.items()}
    for k in sorted(groups, key=lambda k: -(quota[k] - int(quota[k]))):     # largest remainder
        if sum(take.values()) >= n_test:
            break
        if take[k] < len(groups[k]) - 1:
            take[k] += 1
    for k, items in groups.items():
        items = sorted(items, key=lambda e: e["id"])
        rng.shuffle(items)
        for i, e in enumerate(items):
            e["split"] = "test" if i < take[k] else "dev"


def main() -> int:
    w2 = migrate_w2()
    seed, overlap = merge_seed()
    examples = w2 + seed + NEW
    ids = [e["id"] for e in examples]
    assert len(ids) == len(set(ids)) == 100, (len(ids), len(set(ids)))
    for e in examples:
        assert e["category"] in CATEGORIES, e["id"]
        assert e["expect_refusal"] or e["gold_docs"], f"{e['id']}: answerable without gold_docs"
    corpus = REPO / "week3" / "corpus"
    for e in examples:
        for g in e["gold_docs"]:
            assert (corpus / g).exists(), f"{e['id']}: missing gold doc {g}"
    split(examples)
    order = {c: i for i, c in enumerate(CATEGORIES)}
    examples.sort(key=lambda e: (order[e["category"]], e["split"], e["id"]))
    OUT.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in examples), encoding="utf-8")

    by = Counter(e["category"] for e in examples)
    dev = Counter(e["category"] for e in examples if e["split"] == "dev")
    users = defaultdict(set)
    for e in examples:
        if e["category"] == "access":
            users[e["user_id"]].add("refused" if e["expect_refusal"] else "answered")
    L = ["# Dataset v3 — where every example came from", "",
         f"{len(examples)} examples: {sum(1 for e in examples if e['origin'].startswith('week2'))} migrated from Week 2, "
         f"{len(seed)} from the seed set, {len(NEW)} new. Split: dev {sum(dev.values())} / test {len(examples) - sum(dev.values())}.", "",
         "| Category | Total | Dev | Test |", "|---|---:|---:|---:|"]
    for c in CATEGORIES:
        L.append(f"| {c} | {by[c]} | {dev[c]} | {by[c] - dev[c]} |")
    L += ["", "Access examples by user: " + ", ".join(f"{u} {'/'.join(sorted(v))}" for u, v in sorted(users.items())), "",
          "## Seed examples dropped as duplicates of a Week 2 example", ""] + [f"- {n}" for n in overlap]
    L += ["", "## Every example", "", "| id | category | split | user | origin | question |", "|---|---|---|---|---|---|"]
    for e in examples:
        L.append(f"| {e['id']} | {e['category']} | {e['split']} | {e['user_id']} | {e['origin']} | {e['question'][:90]} |")
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:22]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
