"""
Fast tier — the Task 7 eval gate's own logic (offline): the dataset is well formed,
the gate fails when it should and only then, flips are reported by id, the
baseline's majority/flaky logic, and the runner scores an example end to end with a
scripted model (follow-up history included).
"""

import copy
import importlib.util
import json
import re

import pytest
from conftest import DATA_DIR, REPO_ROOT, FakeRetriever, prefix, scripted_llm

GATE_DIR = REPO_ROOT / "week2" / "task_07_eval_gate"
CATEGORIES = {"factual", "multi-hop", "multi-part", "refusal", "follow-up", "keyword"}


def load_script(name):
    spec = importlib.util.spec_from_file_location(f"gate_{name}", GATE_DIR / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def dataset():
    return [json.loads(line) for line in (GATE_DIR / "eval_dataset.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()]


# ===========================================================================
# The dataset
# ===========================================================================

def test_dataset_shape(dataset):
    assert len(dataset) >= 30
    assert len({e["id"] for e in dataset}) == len(dataset)
    assert {e["category"] for e in dataset} == CATEGORIES
    new = [e for e in dataset if e["added_in"] == "week2-task7"]
    assert len(new) == 10
    for cat in ("multi-hop", "multi-part", "refusal", "follow-up", "keyword"):
        assert sum(e["category"] == cat for e in new) >= 2, f"need 2+ new {cat} examples"
    assert all(e.get("designed_to_break") for e in new), "each new example says what it is designed to break"


def test_existing_examples_match_the_capstone_eval(app, dataset):
    """The gate's dataset and `app.py eval` must not silently drift apart."""
    old = [e for e in dataset if e["added_in"] == "week1"]
    assert [(e["question"], e["reference"]) for e in old] == [(q, a) for q, a, _s, _f in app.EVAL_EXAMPLES]


def test_every_example_is_consistent_with_the_corpus(dataset, app):
    corpus = {p.name: " ".join(p.read_text(encoding="utf-8").split()).lower() for p in DATA_DIR.glob("*.md")}
    for e in dataset:
        if e["expect_refusal"]:
            assert not e["facts"] and not e["sources"] and e["reference"] == app.REFUSAL, e["id"]
            continue
        assert e["sources"] and all(s in corpus for s in e["sources"]), e["id"]
        text = " ".join(corpus[s] for s in e["sources"])
        for fact in e["facts"]:
            assert " ".join(fact.split()).lower() in text, f"#{e['id']}: fact {fact!r} not in {e['sources']}"
        if e["category"] == "multi-hop":
            assert len(e["sources"]) >= 2 and len(e["facts"]) >= 2, "multi-hop = facts from two documents"
        if e["category"] == "follow-up":
            assert e["history"], "a follow-up needs its earlier turn"


# ===========================================================================
# The gate
# ===========================================================================

def ex(i, cat, c, g, r=1):
    return {"id": i, "category": cat, "question": f"q{i}", "scores": {"correctness": c, "groundedness": g,
                                                                       "retrieval_hit": r},
            "comments": {"correctness": "judge: X", "groundedness": "judge: Y", "retrieval_hit": ""}}


def results_from(examples, cost=0.0004, version="v1"):
    n = len(examples)
    scores = {m: sum(e["scores"][m] for e in examples) / n for m in ("correctness", "groundedness", "retrieval_hit")}
    cats = {}
    for e in examples:
        cats.setdefault(e["category"], []).append(e)
    return {"meta": {"dataset_version": version, "n": n, "model": "m", "judge": "j", "runner": "r",
                     "wall_clock_s": 1, "git_sha": "abc", "date": "2026-11-16"},
            "scores": scores,
            "by_category": {c: {"n": len(v), **{m: sum(x["scores"][m] for x in v) / len(v)
                                                for m in ("correctness", "groundedness", "retrieval_hit")}}
                            for c, v in cats.items()},
            "cost": {"mean_cost_usd": cost, "mean_llm_calls": 12, "mean_latency_s": 3},
            "examples": examples}


@pytest.fixture
def gate():
    return load_script("check_baseline")


@pytest.fixture
def baseline():
    examples = [ex(i, "factual", 1, 1) for i in range(1, 19)] + [ex(19, "multi-hop", 0, 1), ex(20, "refusal", 1, 1)]
    b = results_from(examples)
    b["tolerance"] = {"correctness": 0.08, "groundedness": 0.08, "cost_increase": 0.20}
    return b


def test_gate_passes_an_identical_run(gate, baseline):
    passed, failures, details = gate.check(results_from(copy.deepcopy(baseline["examples"])), baseline)
    assert passed and not failures and details["flips"] == {"regressed": [], "improved": []}


def test_gate_tolerates_noise_within_the_tolerance(gate, baseline):
    run = copy.deepcopy(baseline["examples"])
    run[0]["scores"]["correctness"] = 0                  # one flip of 20 = -0.05 < 0.08
    passed, _, details = gate.check(results_from(run), baseline)
    assert passed
    assert [f["id"] for f in details["flips"]["regressed"]] == [1], "still reported, by id"


def test_gate_fails_a_real_regression_and_names_the_examples(gate, baseline):
    run = copy.deepcopy(baseline["examples"])
    for e in run[:3]:                                     # three flips = -0.15 > 0.08
        e["scores"]["correctness"] = 0
    passed, failures, details = gate.check(results_from(run), baseline)
    assert not passed and "correctness" in failures[0]
    text = gate.report(results_from(run), baseline, passed, failures, details)
    assert "FAILED" in text and "| 1 | factual | correctness 1 → 0" in text and "| 3 |" in text


def test_gate_fails_on_cost_increase_above_20_percent(gate, baseline):
    same = copy.deepcopy(baseline["examples"])
    assert gate.check(results_from(same, cost=0.0004 * 1.15), baseline)[0], "+15% is within budget"
    passed, failures, _ = gate.check(results_from(same, cost=0.0004 * 1.25), baseline)
    assert not passed and "cost" in failures[0]


def test_gate_main_exit_codes_and_report(gate, baseline, tmp_path):
    b, r, rep = tmp_path / "b.json", tmp_path / "r.json", tmp_path / "report.md"
    b.write_text(json.dumps(baseline))
    run = copy.deepcopy(baseline["examples"])
    r.write_text(json.dumps(results_from(run, version="v2")))
    assert gate.main(["--results", str(r), "--baseline", str(b), "--report", str(rep)]) == 0
    assert "Dataset changed" in rep.read_text()
    for e in run[:4]:
        e["scores"]["groundedness"] = 0
    r.write_text(json.dumps(results_from(run)))
    assert gate.main(["--results", str(r), "--baseline", str(b), "--report", str(rep)]) == 1
    assert "groundedness" in rep.read_text()


def test_gate_never_compares_against_the_archived_week2_baseline(gate, baseline, tmp_path):
    """Week 3 Task 1: the Week 2 baseline describes the 4-file corpus. It is archived as
    eval_baseline_w2.json and must not gate a run, even an identical one; with no current
    baseline the gate is red and says why, instead of comparing against stale numbers."""
    archived = GATE_DIR / "eval_baseline_w2.json"
    assert archived.exists(), "the Week 2 baseline is kept for history"
    r, rep = tmp_path / "r.json", tmp_path / "report.md"
    r.write_text(json.dumps(json.loads(archived.read_text())))          # a run identical to it
    assert gate.main(["--results", str(r), "--baseline", str(archived), "--report", str(rep)]) == 1
    assert "ARCHIVED" in rep.read_text()
    assert gate.main(["--results", str(r), "--baseline", str(tmp_path / "eval_baseline.json"),
                      "--report", str(rep)]) == 1
    assert "NO BASELINE" in rep.read_text() and "eval_baseline_w2.json" in rep.read_text()


def test_baseline_uses_majority_and_marks_flaky_examples(tmp_path):
    make = load_script("make_baseline")
    runs = []
    for c1 in (1, 1, 0):                                  # example 1: 2 of 3 runs correct -> 1, flaky
        examples = [ex(1, "factual", c1, 1), ex(2, "refusal", 1, 1)]
        res = results_from(examples)
        res["meta"]["dataset_version"] = "v1"
        p = tmp_path / f"run{len(runs)}.json"
        p.write_text(json.dumps(res))
        runs.append(str(p))
    just = tmp_path / "why.md"
    just.write_text("because")
    out = tmp_path / "baseline.json"
    assert make.main([*runs, "--tolerance", "0.08", "--justification-file", str(just), "--out", str(out)]) == 0
    b = json.loads(out.read_text())
    e1 = next(e for e in b["examples"] if e["id"] == 1)
    assert e1["scores"]["correctness"] == 1 and e1["flaky"]["correctness"] is True
    assert b["tolerance"]["correctness"] == 0.08 and b["tolerance_justification"] == "because"
    assert b["noise"]["examples_with_disagreeing_runs"]["correctness"] == [1]
    assert b["scores"]["correctness"] == pytest.approx((1 + 1 + 0.5) / 3, abs=1e-3)


# ===========================================================================
# The runner (offline)
# ===========================================================================

def test_runner_scores_examples_and_injects_follow_up_history(app, sample_docs, dataset, monkeypatch):
    run_eval = load_script("run_eval")
    from app.config import get_settings

    llm = scripted_llm(app, standalone="Do the paid sick days carry over?")
    judge = scripted_llm(app)
    judge.rules[prefix(app.CORRECTNESS_PROMPT)] = "Key facts checked.\nVERDICT: CORRECT"
    assistant = app.Assistant(FakeRetriever(sample_docs), llm)
    evaluators = app.make_evaluators(judge)
    follow_up = next(e for e in dataset if e["category"] == "follow-up")
    row = run_eval.score_example(assistant, evaluators, follow_up, get_settings(), "test")

    [ctx_prompt] = llm.calls_to(prefix(app.CONTEXTUALIZE_PROMPT))
    assert follow_up["history"][0][0] in ctx_prompt, "the earlier turn was in the session"
    assert row["standalone"] == "Do the paid sick days carry over?"
    assert set(row["scores"]) == {"correctness", "groundedness", "retrieval_hit"}
    assert row["scores"]["correctness"] == 1 and "error" not in row
    [corr] = judge.calls_to(prefix(app.CORRECTNESS_PROMPT))
    assert "Earlier in the conversation" in corr, "the judge sees the history too"

    refusal = next(e for e in dataset if e["expect_refusal"])
    llm.rules[prefix(app.ROUTE_PROMPT)] = "DIRECT"
    r2 = run_eval.score_example(assistant, evaluators, refusal, get_settings(), "test")
    assert r2["refused"] is True and r2["scores"]["correctness"] == 1
    agg = run_eval.aggregate([row, r2])
    assert set(agg["by_category"]) == {"follow-up", "refusal"} and agg["scores"]["correctness"] == 1.0


def test_runner_turns_a_pipeline_error_into_a_zero_not_a_crash(app, dataset):
    run_eval = load_script("run_eval")
    from app.config import get_settings

    class Broken:
        sessions = {}

        def stream(self, *a, **k):
            raise RuntimeError("model server down")
            yield

    row = run_eval.score_example(Broken(), [None, None, None], dataset[0], get_settings(), "t")
    assert row["scores"] == {"correctness": 0, "groundedness": 0, "retrieval_hit": 0}
    assert "model server down" in row["error"]


# ===========================================================================
# The workflow
# ===========================================================================

def test_ci_workflow_wires_both_gates():
    import yaml

    wf = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    on = wf.get("on", wf.get(True))                       # YAML 1.1 reads `on:` as True
    assert {"pull_request", "schedule", "workflow_dispatch"} <= set(on)
    assert "labeled" in on["pull_request"]["types"]
    fast, gate_job = wf["jobs"]["fast-checks"], wf["jobs"]["eval-gate"]
    assert fast.get("timeout-minutes") and "run-eval" in gate_job["if"]
    steps = " ".join(str(s.get("run", "")) for s in gate_job["steps"])
    assert "run_eval.py" in steps and "check_baseline.py" in steps
    assert "OPENAI_API_KEY" not in json.dumps(fast), "the fast tier gets no secrets"
    assert re.search(r"pytest .*not live", " ".join(str(s.get("run", "")) for s in fast["steps"]))
