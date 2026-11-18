# Dataset v3 — where every example came from

100 examples: 38 migrated from Week 2, 30 from the seed set, 32 new. Split: dev 70 / test 30.

| Category | Total | Dev | Test |
|---|---:|---:|---:|
| factual | 14 | 10 | 4 |
| table | 6 | 4 | 2 |
| keyword | 6 | 4 | 2 |
| version | 7 | 5 | 2 |
| conflict | 5 | 3 | 2 |
| draft | 5 | 4 | 1 |
| multi_hop | 6 | 4 | 2 |
| multi_part | 6 | 4 | 2 |
| ambiguous | 5 | 3 | 2 |
| long_doc | 5 | 4 | 1 |
| cross_lingual | 6 | 4 | 2 |
| follow_up | 5 | 4 | 1 |
| personalized | 6 | 4 | 2 |
| access | 10 | 7 | 3 |
| out_of_scope | 8 | 6 | 2 |

Access examples by user: u1001 refused, u1002 refused, u1003 refused, u2001 answered, u3001 answered/refused, u3002 answered

## Seed examples dropped as duplicates of a Week 2 example

- s01 (factual) duplicates Week 2 #5: kept #5
- s02 (version) duplicates Week 2 #2: kept #2
- s03 (version) duplicates Week 2 #9: kept #9
- s05 (conflict) duplicates Week 2 #18: kept #18
- s13 (multi_part) duplicates Week 2 #17: kept #17
- s14 (multi_part) duplicates Week 2 #13: kept #13
- s16 (out_of_scope) duplicates Week 2 #26: kept #26
- s30 (version) duplicates Week 2 #15: kept #15
- s31 (version) duplicates Week 2 #8: kept #8
- s39 (table) duplicates Week 2 #10: kept #10

## Every example

| id | category | split | user | origin | question |
|---|---|---|---|---|---|
| 11 | factual | dev | u1001 | week2 #11 (factual; Task 1 verdict: unchanged) | Is alcohol reimbursable? |
| 12 | factual | dev | u1001 | week2 #12 (factual; Task 1 verdict: regression) | How long do I have to file an expense report? |
| 19 | factual | dev | u1001 | week2 #19 (factual; Task 1 verdict: unchanged) | Can I open our source code on my personal phone? |
| 20 | factual | dev | u1001 | week2 #20 (factual; Task 1 verdict: regression) | Do I need approval for a Figma license? |
| 24 | factual | dev | u1001 | week2 #24 (factual; Task 1 verdict: bad test) | Can the R2 be used outdoors? |
| 4 | factual | dev | u1001 | week2 #4 (factual; Task 1 verdict: unchanged) | How far ahead do I have to ask for PTO? |
| 5 | factual | dev | u1001 | week2 #5 (factual; Task 1 verdict: unchanged) | How many sick days are there per year? |
| 6 | factual | dev | u1001 | week2 #6 (factual; Task 1 verdict: unchanged) | When do I need a doctor's note? |
| 7 | factual | dev | u1001 | week2 #7 (factual; Task 1 verdict: unchanged) | How many days a week can I work from home? |
| s29 | factual | dev | u1001 | seed | How quickly do I have to report a lost laptop? |
| 14 | factual | test | u1001 | week2 #14 (factual; Task 1 verdict: unchanged) | How often are performance reviews held? |
| 21 | factual | test | u1001 | week2 #21 (factual; Task 1 verdict: unchanged) | How much weight can the Warehouse Rover R2 carry? |
| s33 | factual | test | u1001 | seed | How much is the primary on-call stipend? |
| s37 | factual | test | u1001 | seed | When will Fleet Manager REST API v1 be removed? |
| 10 | table | dev | u1001 | week2 #10 (factual; Task 1 verdict: world changed) | What is the daily meal limit when travelling abroad? |
| n01 | table | dev | u1001 | new (hand-written) | What is the hotel cap per night for a business trip to India? |
| n02 | table | dev | u1001 | new (LLM-generated c009, reviewed) | How much does the 5G connectivity module cost? |
| s06 | table | dev | u1001 | seed | What is the hotel cap per night for a business trip to Germany? |
| n03 | table | test | u1001 | new (LLM-generated c007, reviewed) | How quickly do Premium Plus customers receive critical spare parts? |
| s35 | table | test | u1001 | seed | What is the first response time on the Premium Plus support plan? |
| 37 | keyword | dev | u1001 | week2 #37 (keyword; Task 1 verdict: world changed) | What did Fleet Manager 4.3 add? |
| 38 | keyword | dev | u1001 | week2 #38 (keyword; Task 1 verdict: unchanged) | Does the R2 support 5G? |
| n04 | keyword | dev | u1001 | new (LLM-generated c045, reviewed) | How do I fix error E-301? |
| s34 | keyword | dev | u1001 | seed | What does error E-271 indicate? |
| s08 | keyword | test | u1001 | seed | What does error code E-217 mean? |
| s09 | keyword | test | u1001 | seed | Is part NW-BAT-4830 compatible with the R2? |
| 15 | version | dev | u1001 | week2 #15 (factual; Task 1 verdict: world changed) | What is my annual learning budget? |
| 3 | version | dev | u1001 | week2 #3 (factual; Task 1 verdict: world changed) | Can I take time off in my first months? |
| 8 | version | dev | u1001 | week2 #8 (factual; Task 1 verdict: world changed) | What is the home-office stipend? |
| 9 | version | dev | u1001 | week2 #9 (factual; Task 1 verdict: world changed) | How long is paid leave for an adoptive parent? |
| s32 | version | dev | u1001 | seed | Can I work from another country for a few weeks? |
| 2 | version | test | u1001 | week2 #2 (factual; Task 1 verdict: world changed) | time off carry rules? |
| s04 | version | test | u1001 | seed | What is the minimum length for a corporate password? |
| 18 | conflict | dev | u1001 | week2 #18 (multi-part; Task 1 verdict: world changed) | How do I get on the VPN from home? |
| n06 | conflict | dev | u1003 | new (hand-written) | The sales IT tips say passwords need 12 characters and must be changed every 90 days. Is t |
| n07 | conflict | dev | u1002 | new (LLM-generated c053, reviewed, re-categorised as conflict) | How many days a week can I work remotely during Ramadan? |
| n05 | conflict | test | u1003 | new (hand-written) | I lost my laptop at a trade show. Is it OK to email IT the next morning? |
| s38 | conflict | test | u1003 | seed | Do I need to change my password every 90 days? |
| n08 | draft | dev | u1001 | new (hand-written) | Is Northwind switching to flexible time off? |
| n09 | draft | dev | u1001 | new (hand-written) | What is the minimum amount of time off I must take under the flexible time off policy? |
| n10 | draft | dev | u1001 | new (hand-written) | By when can I send comments on the flexible time off proposal? |
| n11 | draft | dev | u1001 | new (hand-written) | Has PTO carry-over been abolished? |
| s17 | draft | test | u1001 | seed | Do we have unlimited PTO? |
| 29 | multi_hop | dev | u1001 | week2 #29 (multi-hop; Task 1 verdict: world changed) | I just referred a friend who got hired. When do I get my referral bonus, and when will my  |
| 30 | multi_hop | dev | u1001 | week2 #30 (multi-hop; Task 1 verdict: world changed) | I want to work fully remote. What do I need to get approved, and how do I reach internal s |
| n23 | multi_hop | dev | u1001 | new (hand-written) | My rover has shown E-217 three times today. Which part should be replaced, and what does i |
| s07 | multi_hop | dev | u1001 | seed | What is the daily meal allowance when I travel to Cairo? |
| n18 | multi_hop | test | u1001 | new (hand-written) | We only run Fleet Manager 4.3. Can we add an R3 to our fleet? |
| s36 | multi_hop | test | u1001 | seed | Can an R2 be managed by Fleet Manager 5.0? |
| 13 | multi_part | dev | u1001 | week2 #13 (multi-part; Task 1 verdict: world changed) | How much is the referral bonus and when is it paid? |
| 16 | multi_part | dev | u1001 | week2 #16 (multi-part; Task 1 verdict: world changed) | My laptop got stolen, what do I do? |
| 17 | multi_part | dev | u1001 | week2 #17 (multi-part; Task 1 verdict: world changed) | What are the password rules? |
| 32 | multi_part | dev | u1001 | week2 #32 (multi-part; Task 1 verdict: world changed) | What are the rules for booking business travel? |
| 23 | multi_part | test | u1001 | week2 #23 (multi-part; Task 1 verdict: unchanged) | What does premium support include? |
| 31 | multi_part | test | u1001 | week2 #31 (multi-part; Task 1 verdict: regression) | What are the known limitations of the Warehouse Rover R2? |
| n20 | ambiguous | dev | u1001 | new (hand-written) | Which battery pack does the rover use? |
| n21 | ambiguous | dev | u1001 | new (hand-written) | Which Fleet Manager version do I need for the rover? |
| s12 | ambiguous | dev | u1001 | seed | What is the payload capacity of the rover? |
| 22 | ambiguous | test | u1001 | week2 #22 (factual; Task 1 verdict: unchanged) | How fast does the rover go with a load? |
| n19 | ambiguous | test | u1001 | new (hand-written) | How long is parental leave? |
| n12 | long_doc | dev | u1001 | new (LLM-generated c023, reviewed, merged with c024) | How should I prepare an R3 for storage of more than a month? |
| n13 | long_doc | dev | u1001 | new (LLM-generated c026, reviewed) | How high a threshold can the R3 cross? |
| n14 | long_doc | dev | u1001 | new (hand-written) | Can the R3 work on an outdoor loading dock in hot weather? |
| s10 | long_doc | dev | u1001 | seed | What is the maximum ramp incline for a loaded R3? |
| s11 | long_doc | test | u1001 | seed | How do I reset the emergency stop on an R3? |
| n15 | cross_lingual | dev | u1002 | new (LLM-generated c050, reviewed) | What are the Cairo office's opening hours? |
| n16 | cross_lingual | dev | u1002 | new (LLM-generated c051, reviewed) | How much does it cost to replace a lost access badge at the Cairo office? |
| n17 | cross_lingual | dev | u1002 | new (LLM-generated c055, reviewed) | How many days off is Eid al-Fitr in 2026 for the Cairo office? |
| s25 | cross_lingual | dev | u1002 | seed | Which days make up the work week in the Cairo office? |
| s23 | cross_lingual | test | u1002 | seed | What are the Cairo office working hours during Ramadan? |
| s24 | cross_lingual | test | u1002 | seed | How much is the monthly transport allowance for Cairo employees? |
| 36 | follow_up | dev | u1001 | week2 #36 (follow-up; Task 1 verdict: unchanged) | And what does the standard plan cover? |
| n22 | follow_up | dev | u1001 | new (hand-written) | And how fast does it go when it's loaded? |
| s26 | follow_up | dev | u1001 | seed | And how many of them can I carry over? |
| s27 | follow_up | dev | u1001 | seed | What about Egypt? |
| 35 | follow_up | test | u1001 | week2 #35 (follow-up; Task 1 verdict: unchanged) | Do they carry over? |
| n24 | personalized | dev | u3001 | new (hand-written) | How many PTO days do I get this year? |
| n25 | personalized | dev | u1003 | new (hand-written) | How much annual PTO am I entitled to? |
| n26 | personalized | dev | u1001 | new (hand-written) | Do I get the monthly transport allowance? |
| s28 | personalized | dev | u1001 | seed | How many PTO days am I entitled to this year? |
| 1 | personalized | test | u1002 | week2 #1 (factual; Task 1 verdict: world changed) | How many vacation days do I get a year? |
| n27 | personalized | test | u1001 | new (LLM-generated c056, reviewed, rewritten as personalized) | Is January 19 a company holiday for me? |
| n28 | access | dev | u1002 | new (hand-written) | What is the merit budget for the 2026 compensation review? |
| n32 | access | dev | u2001 | new (hand-written) | How long is a performance improvement plan? |
| s18 | access | dev | u1001 | seed | What is the salary range for an L4 engineer in Austin? |
| s19 | access | dev | u3001 | seed | What is the salary range for an L4 engineer in Austin? |
| s20 | access | dev | u1001 | seed | What is Project Juniper? |
| s21 | access | dev | u2001 | seed | What target rating distribution should I use in performance calibration? |
| s22 | access | dev | u1001 | seed | How long is a performance improvement plan? |
| n29 | access | test | u3002 | new (hand-written) | When will employees affected by Project Juniper be informed? |
| n30 | access | test | u3001 | new (hand-written) | What is Project Juniper? |
| n31 | access | test | u1003 | new (hand-written) | What target rating distribution should managers use in calibration? |
| 25 | out_of_scope | dev | u1001 | week2 #25 (refusal; Task 1 verdict: unchanged) | What is the capital of France? |
| 26 | out_of_scope | dev | u1001 | week2 #26 (refusal; Task 1 verdict: unchanged) | What is the CEO's home address? |
| 27 | out_of_scope | dev | u1001 | week2 #27 (refusal; Task 1 verdict: unchanged) | What dental insurance plan does Northwind offer? |
| 33 | out_of_scope | dev | u1001 | week2 #33 (refusal; Task 1 verdict: unchanged) | How many days of bereavement leave do I get? |
| s15 | out_of_scope | dev | u1001 | seed | What is the company policy on bringing dogs to the office? |
| s40 | out_of_scope | dev | u1001 | seed | What is Northwind Robotics' current share price? |
| 28 | out_of_scope | test | u1001 | week2 #28 (refusal; Task 1 verdict: unchanged) | Who won the football match last night? |
| 34 | out_of_scope | test | u1001 | week2 #34 (refusal; Task 1 verdict: unchanged) | What is the maximum operating temperature of the Warehouse Rover R2? |
