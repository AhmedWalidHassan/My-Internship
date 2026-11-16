# Cost report — 2026-11-16 11:28

Model: ollama:qwen3.5:4b   pricing: $0.00015/1K in, $0.0006/1K out   k=4   MAX_DOCS_TO_GRADE=2
28 questions (4 out-of-scope), 28 ok, 0 errors, wall clock 69 s

## 1. Per question

| # | Question | Latency | LLM calls | Tokens in / out | Cost | Path len | Rewrites | Refused |
|---:|---|---:|---:|---:|---:|---:|---:|---|
| 1 | How many vacation days do I get a year? | 2.5 s | 9 | 1,569 / 100 | $0.000295 | 9 | 1 |  |
| 2 | time off carry rules? | 1.2 s | 6 | 1,002 / 44 | $0.000177 | 6 | 0 |  |
| 3 | Can I take time off in my first months? | 3.6 s | 6 | 1,365 / 195 | $0.000322 | 6 | 0 |  |
| 4 | How far ahead do I have to ask for PTO? | 1.9 s | 6 | 1,273 / 76 | $0.000237 | 6 | 0 |  |
| 5 | How many sick days are there per year? | 1.7 s | 6 | 1,274 / 64 | $0.000229 | 6 | 0 |  |
| 6 | When do I need a doctor's note? | 1.7 s | 6 | 1,026 / 66 | $0.000193 | 6 | 0 |  |
| 7 | How many days a week can I work from home? | 2.0 s | 6 | 1,105 / 86 | $0.000217 | 6 | 0 |  |
| 8 | What is the home-office stipend? | 1.5 s | 6 | 1,074 / 64 | $0.000199 | 6 | 0 |  |
| 9 | How long is paid leave for an adoptive parent? | 2.6 s | 6 | 1,031 / 127 | $0.000231 | 6 | 0 |  |
| 10 | What is the daily meal limit when travelling … | 2.8 s | 11 | 2,133 / 120 | $0.000392 | 13 | 2 | yes |
| 11 | Is alcohol reimbursable? | 2.8 s | 12 | 2,177 / 94 | $0.000383 | 12 | 2 |  |
| 12 | How long do I have to file an expense report? | 1.8 s | 6 | 1,159 / 72 | $0.000217 | 6 | 0 |  |
| 13 | How much is the referral bonus and when is it… | 2.1 s | 6 | 1,081 / 96 | $0.000220 | 6 | 0 |  |
| 14 | How often are performance reviews held? | 1.9 s | 6 | 965 / 82 | $0.000194 | 6 | 0 |  |
| 15 | What is my annual learning budget? | 2.6 s | 6 | 1,087 / 121 | $0.000236 | 6 | 0 |  |
| 16 | My laptop got stolen, what do I do? | 2.7 s | 6 | 1,175 / 131 | $0.000255 | 6 | 0 |  |
| 17 | What are the password rules? | 2.7 s | 9 | 1,789 / 119 | $0.000340 | 9 | 1 |  |
| 18 | How do I get on the VPN from home? | 3.9 s | 6 | 1,249 / 208 | $0.000312 | 6 | 0 |  |
| 19 | Can I open our source code on my personal phone? | 3.3 s | 12 | 2,275 / 144 | $0.000428 | 12 | 2 |  |
| 20 | Do I need approval for a Figma license? | 6.5 s | 15 | 2,777 / 339 | $0.000620 | 17 | 2 | yes |
| 21 | How much weight can the Warehouse Rover R2 ca… | 2.4 s | 11 | 1,947 / 94 | $0.000348 | 13 | 2 | yes |
| 22 | How fast does the rover go with a load? | 1.7 s | 6 | 1,321 / 57 | $0.000232 | 6 | 0 |  |
| 23 | What does premium support include? | 3.1 s | 6 | 1,048 / 163 | $0.000255 | 6 | 0 |  |
| 24 | Can the R2 be used outdoors? | 3.8 s | 11 | 1,872 / 173 | $0.000385 | 13 | 2 | yes |
| 25 | What is the capital of France? | 0.3 s | 2 | 210 / 4 | $0.000034 | 3 | 0 | yes |
| 26 | What is the CEO's home address? | 2.8 s | 11 | 2,353 / 97 | $0.000411 | 13 | 2 | yes |
| 27 | What dental insurance plan does Northwind offer? | 2.7 s | 11 | 2,169 / 93 | $0.000381 | 13 | 2 | yes |
| 28 | Who won the football match last night? | 0.2 s | 2 | 212 / 4 | $0.000034 | 3 | 0 | yes |

## 2. Aggregate

| Metric | Value |
|---|---:|
| Mean latency per question | 2.46 s |
| p95 latency per question | 3.86 s |
| Mean LLM calls per question | 7.6 (p95 12, max 15) |
| Mean tokens per question (in / out) | 1,418 / 108 |
| Mean cost per question | $0.000278 |
| **Projected monthly cost @ 1,000 questions/day** | **$8.33** |
| Refusal rate / mean rewrites | 29% / 0.64 |

## 3. Per node (sorted by cost)

| Node | LLM calls / question | Tokens in / out per question | Cost / question | % of spend | Time / question | % of time |
|---|---:|---:|---:|---:|---:|---:|
| `grade_documents` | 3.14 | 547 / 6 | $0.000086 | 30.9% | 0.38 s | 15.4% |
| `grade_generation` | 1.71 | 347 / 56 | $0.000085 | 30.8% | 1.05 s | 42.8% |
| `generate` | 1.00 | 305 / 33 | $0.000065 | 23.5% | 0.65 s | 26.3% |
| `route_question` | 1.00 | 147 / 5 | $0.000025 | 9.0% | 0.18 s | 7.1% |
| `rewrite_query` | 0.64 | 67 / 9 | $0.000015 | 5.5% | 0.19 s | 7.6% |
| `direct_answer` | 0.07 | 5 / 0 | $0.000001 | 0.3% | 0.01 s | 0.3% |
| `contextualize` | 0.00 | 0 / 0 | $0.000000 | 0.0% | 0.00 s | 0.0% |
| `retrieve` | 0.00 | 0 / 0 | $0.000000 | 0.0% | 0.01 s | 0.4% |
| `refuse` | 0.00 | 0 / 0 | $0.000000 | 0.0% | 0.00 s | 0.0% |

## 4. Node-path distribution

| Path | Count | % |
|---|---:|---:|
| route → retrieve → grade → generate → check → END (answered) | 16 | 57% |
| …with 2 rewrite loops (refused) | 6 | 21% |
| …with 1 rewrite loop (answered) | 2 | 7% |
| …with 2 rewrite loops (answered) | 2 | 7% |
| route → direct → END | 2 | 7% |

Rewrite loop fired on **10 of 28** questions (36%), 18 rewrites in total. What triggered them:
- doc grader rejected every passage: 16
- fact-check rejected the answer: 2
