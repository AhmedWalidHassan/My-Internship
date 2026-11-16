# Cost report — 2026-11-16 11:17

Model: ollama:qwen3.5:4b   pricing: $0.00015/1K in, $0.0006/1K out   k=4   MAX_DOCS_TO_GRADE=6
28 questions (4 out-of-scope), 28 ok, 0 errors, wall clock 92 s

## 1. Per question

| # | Question | Latency | LLM calls | Tokens in / out | Cost | Path len | Rewrites | Refused |
|---:|---|---:|---:|---:|---:|---:|---:|---|
| 1 | How many vacation days do I get a year? | 2.2 s | 10 | 1,900 / 80 | $0.000333 | 6 | 0 |  |
| 2 | time off carry rules? | 3.8 s | 10 | 1,949 / 190 | $0.000406 | 6 | 0 |  |
| 3 | Can I take time off in my first months? | 8.7 s | 19 | 4,142 / 436 | $0.000883 | 11 | 1 |  |
| 4 | How far ahead do I have to ask for PTO? | 2.4 s | 10 | 1,937 / 84 | $0.000341 | 6 | 0 |  |
| 5 | How many sick days are there per year? | 2.1 s | 9 | 1,712 / 70 | $0.000299 | 6 | 0 |  |
| 6 | When do I need a doctor's note? | 2.2 s | 10 | 1,756 / 74 | $0.000308 | 6 | 0 |  |
| 7 | How many days a week can I work from home? | 2.8 s | 10 | 2,033 / 108 | $0.000370 | 6 | 0 |  |
| 8 | What is the home-office stipend? | 2.2 s | 10 | 1,743 / 72 | $0.000305 | 6 | 0 |  |
| 9 | How long is paid leave for an adoptive parent? | 3.1 s | 10 | 1,756 / 135 | $0.000344 | 6 | 0 |  |
| 10 | What is the daily meal limit when travelling … | 3.0 s | 17 | 2,872 / 86 | $0.000482 | 9 | 1 |  |
| 11 | Is alcohol reimbursable? | 4.4 s | 24 | 4,399 / 127 | $0.000736 | 12 | 2 |  |
| 12 | How long do I have to file an expense report? | 2.4 s | 10 | 1,883 / 80 | $0.000330 | 6 | 0 |  |
| 13 | How much is the referral bonus and when is it… | 2.7 s | 10 | 1,806 / 104 | $0.000333 | 6 | 0 |  |
| 14 | How often are performance reviews held? | 2.5 s | 10 | 1,747 / 90 | $0.000316 | 6 | 0 |  |
| 15 | What is my annual learning budget? | 3.1 s | 10 | 1,807 / 129 | $0.000348 | 6 | 0 |  |
| 16 | My laptop got stolen, what do I do? | 3.0 s | 8 | 1,603 / 135 | $0.000321 | 6 | 0 |  |
| 17 | What are the password rules? | 2.9 s | 10 | 1,939 / 110 | $0.000357 | 6 | 0 |  |
| 18 | How do I get on the VPN from home? | 4.4 s | 9 | 1,811 / 214 | $0.000400 | 6 | 0 |  |
| 19 | Can I open our source code on my personal phone? | 5.2 s | 24 | 4,509 / 172 | $0.000780 | 12 | 2 |  |
| 20 | Do I need approval for a Figma license? | 7.8 s | 25 | 4,522 / 359 | $0.000894 | 17 | 2 | yes |
| 21 | How much weight can the Warehouse Rover R2 ca… | 2.1 s | 10 | 2,010 / 59 | $0.000337 | 6 | 0 |  |
| 22 | How fast does the rover go with a load? | 2.2 s | 10 | 2,030 / 65 | $0.000343 | 6 | 0 |  |
| 23 | What does premium support include? | 3.6 s | 10 | 1,626 / 171 | $0.000346 | 6 | 0 |  |
| 24 | Can the R2 be used outdoors? | 4.5 s | 22 | 3,872 / 149 | $0.000670 | 12 | 2 |  |
| 25 | What is the capital of France? | 0.2 s | 2 | 210 / 4 | $0.000034 | 3 | 0 | yes |
| 26 | What is the CEO's home address? | 4.2 s | 23 | 4,396 / 120 | $0.000731 | 13 | 2 | yes |
| 27 | What dental insurance plan does Northwind offer? | 4.3 s | 23 | 4,493 / 122 | $0.000747 | 13 | 2 | yes |
| 28 | Who won the football match last night? | 0.2 s | 2 | 212 / 4 | $0.000034 | 3 | 0 | yes |

## 2. Aggregate

| Metric | Value |
|---|---:|
| Mean latency per question | 3.28 s |
| p95 latency per question | 6.89 s |
| Mean LLM calls per question | 12.8 (p95 24, max 25) |
| Mean tokens per question (in / out) | 2,381 / 127 |
| Mean cost per question | $0.000433 |
| **Projected monthly cost @ 1,000 questions/day** | **$12.99** |
| Refusal rate / mean rewrites | 18% / 0.50 |

## 3. Per node (sorted by cost)

| Node | LLM calls / question | Tokens in / out per question | Cost / question | % of spend | Time / question | % of time |
|---|---:|---:|---:|---:|---:|---:|
| `grade_documents` | 8.29 | 1,442 / 17 | $0.000226 | 52.2% | 1.08 s | 33.0% |
| `grade_generation` | 1.86 | 395 / 62 | $0.000097 | 22.3% | 1.16 s | 35.4% |
| `generate` | 1.04 | 340 / 37 | $0.000073 | 16.8% | 0.71 s | 21.7% |
| `route_question` | 1.00 | 147 / 5 | $0.000025 | 5.8% | 0.18 s | 5.3% |
| `rewrite_query` | 0.50 | 52 / 6 | $0.000012 | 2.7% | 0.13 s | 4.1% |
| `direct_answer` | 0.07 | 5 / 0 | $0.000001 | 0.2% | 0.01 s | 0.2% |
| `contextualize` | 0.00 | 0 / 0 | $0.000000 | 0.0% | 0.00 s | 0.0% |
| `retrieve` | 0.00 | 0 / 0 | $0.000000 | 0.0% | 0.01 s | 0.3% |
| `refuse` | 0.00 | 0 / 0 | $0.000000 | 0.0% | 0.00 s | 0.0% |

## 4. Node-path distribution

| Path | Count | % |
|---|---:|---:|
| route → retrieve → grade → generate → check → END (answered) | 18 | 64% |
| …with 2 rewrite loops (answered) | 3 | 11% |
| …with 2 rewrite loops (refused) | 3 | 11% |
| …with 1 rewrite loop (answered) | 2 | 7% |
| route → direct → END | 2 | 7% |

Rewrite loop fired on **8 of 28** questions (29%), 14 rewrites in total. What triggered them:
- doc grader rejected every passage: 11
- fact-check rejected the answer: 3
