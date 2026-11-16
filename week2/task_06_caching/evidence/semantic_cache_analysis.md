# Semantic cache: can a threshold tell paraphrases from near-misses?

Embedding model: `sentence-transformers/all-MiniLM-L6-v2` (the assistant's own). Cosine similarity of each pair.

## Paraphrases (same answer: a semantic cache should hit)

| Cosine | Question A | Question B |
|---:|---|---|
| 0.948 | My laptop got stolen, what do I do? | What should I do if my laptop is stolen? |
| 0.848 | How often are performance reviews held? | When are performance reviews? |
| 0.804 | What are the password rules? | What is the password policy? |
| 0.804 | How many sick days are there per year? | How many paid sick days do I get? |
| 0.761 | How do I get on the VPN from home? | How do I connect to the VPN remotely? |
| 0.745 | What is my annual learning budget? | How much training budget do I get per year? |
| 0.661 | Is alcohol reimbursable? | Can I expense alcohol? |
| 0.613 | How long do I have to file an expense report? | What's the deadline for submitting expenses? |
| 0.583 | How much weight can the Warehouse Rover R2 carry? | What is the R2's payload capacity? |
| 0.186 | How many vacation days do I get a year? | How much PTO do I get? |

## Near-misses (different answer: a semantic cache must NOT hit)

| Cosine | Question A | Question B | Different answers |
|---:|---|---|---|
| 0.977 | How fast does the rover go with a load? | How fast does the rover go without a load? | 1.8 vs 2.2 m/s |
| 0.912 | What is the daily meal limit when travelling abroad? | What is the daily meal limit for domestic travel? | $110 vs $75 |
| 0.827 | How long is paid leave for an adoptive parent? | How long is paid leave for a birth parent? | 10 vs 16 weeks |
| 0.759 | How many vacation days do I get a year? | How many sick days do I get a year? | 20 vs 10 |
| 0.638 | What does premium support include? | What does standard support include? | 24/7 + 1 h SLA vs business hours + 4 h |
| 0.633 | Can I open our source code on my personal phone? | Can I open my email on my personal phone? | prohibited vs allowed |
| 0.511 | Is alcohol reimbursable? | Are meals reimbursable? | no vs up to $75/$110 a day |
| 0.384 | Can I carry over unused PTO? | Can I carry over unused learning budget? | up to 5 days vs no |
| 0.318 | How far ahead do I have to ask for PTO? | How long do I have to file an expense report? | 5 business days ahead vs within 30 days |
| 0.306 | What is the home-office stipend? | What is the annual learning budget? | $500 vs $1,500 |

## Per threshold

| Threshold | Paraphrases served from cache (good) | Near-misses served the WRONG answer |
|---:|---:|---:|
| 0.70 | 6/10 | **4/10** |
| 0.75 | 5/10 | **4/10** |
| 0.80 | 4/10 | **3/10** |
| 0.85 | 1/10 | **2/10** |
| 0.90 | 1/10 | **2/10** |
| 0.95 | 0/10 | **1/10** |

Highest near-miss similarity: **0.977**. Lowest paraphrase similarity: 0.186. Paraphrases above the highest near-miss: **0/10**.
