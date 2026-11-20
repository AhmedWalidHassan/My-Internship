"""Task 5 — a few questions through the real system (real model), printed with their sources.

    AS_OF_DATE=2026-02-15 python week3/task_05_time_and_truth/scripts_live_check.py
"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.capstone import load_capstone  # noqa: E402

QUESTIONS = sys.argv[1:] or [
    "How many PTO days can I carry over into next year?",
    "Is Northwind switching to flexible time off?",
    "How do I get on the VPN from home?",
    "The sales IT tips say passwords need 12 characters and must be changed every 90 days. Is that right?",
    "What is the payload capacity of the rover?",
]
cap = load_capstone()
backend = cap.Backend()
print("AS_OF_DATE:", cap.SETTINGS.as_of_date, flush=True)
for q in QUESTIONS:
    r = backend.assistant.ask(q, f"live-{uuid.uuid4()}")
    print(f"\nQ: {q}\nA: {r['answer']}\nSources: {[cap.source_label(s) for s in r['sources']]}\n"
          f"Cited: {r['cited_versions']}  path: {' -> '.join(r['path'])}", flush=True)
