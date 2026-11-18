"""
Input guardrails (Week 2, Task 8): reject obvious prompt-injection attempts before they
cost a model call.

What is actually being protected: not the system prompt (it is in the repo), but the
REFUSAL BEHAVIOUR. An input that gets the assistant to answer from its own knowledge
instead of the documents has defeated the product.

Defence in depth, and this check is only the first, cheapest layer:
  1. this pattern check (deterministic, ~0.1 ms, catches the textbook phrasings);
  2. the graph: off-topic questions get a FIXED refusal (no free-form reply), and every
     answer must pass the fact-check against the retrieved documents, so "answer from
     your own knowledge" produces an answer the fact-check rejects;
  3. the prompts never contain secrets, so a leak would be embarrassing, not harmful.

The patterns target instructions ABOUT the assistant (its rules, prompt, role, mode),
so ordinary questions containing "act as" or "ignore" are not caught. A
false positive costs a user one rephrase; a regex will never catch every injection,
which is why layers 2 and 3 exist and are tested end to end.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_PATTERNS: list[tuple[str, str]] = [
    ("override_instructions", r"\b(ignore|disregard|forget|override|bypass|skip)\b[^.?!]{0,40}"
                              r"\b(instruction|instructions|rules?|prompt|guidelines?|polic(y|ies)|context|documents?)\b"),
    ("reveal_prompt", r"\b(print|show|reveal|repeat|output|display|tell me|what (is|are))\b[^.?!]{0,30}"
                      r"\b(system|initial|hidden|original|your)\s+(prompt|instructions|rules)\b"),
    ("role_change", r"\byou\s+are\s+(now|no longer)\b|\bfrom\s+now\s+on\b[^.?!]{0,30}\byou\b"),
    ("mode_switch", r"\b(developer|dev|debug|god|admin|jailbreak|unrestricted|dan)\s+mode\b"),
    ("persona", r"\b(pretend|roleplay|role-play|act)\b[^.?!]{0,20}\b(you are|to be|as an? (ai|assistant|model|chatbot))\b"),
    ("own_knowledge", r"\b(use|answer (from|with|using)|rely on)\b[^.?!]{0,20}\b(your own|general|outside|"
                      r"world|prior|training)\s+knowledge\b|\bwithout\s+(using|the|any)\s+(documents?|context|sources)\b"),
]
_COMPILED = [(name, re.compile(rx, re.IGNORECASE)) for name, rx in _PATTERNS]


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    rule: str | None = None


def check_question(question: str) -> Verdict:
    text = unicodedata.normalize("NFKC", question)
    text = re.sub(r"[​-‏⁠﻿]", "", text)        # zero-width characters used to dodge filters
    text = " ".join(text.split())
    for name, rx in _COMPILED:
        if rx.search(text):
            return Verdict(False, name)
    return Verdict(True)
