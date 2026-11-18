# Seed eval — recursive

- date 2026-11-18T08:48:35+00:00, git `9ca3dcc`, dataset `d73feb361d7a` (40 examples)
- corpus `/tmp/northwind_w3_recursive_view`: **119 files, 146 chunks indexed**
- model ollama:qwen3.5:4b, judge ollama:qwen3.5:4b (same model as the generator: the Week 2 judges), wall clock 279 s

| Category | n | Deterministic pass | Correctness | Groundedness | Refused | Gold doc indexed | Gold doc retrieved | Gold doc kept by grader |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| factual | 4 | 50% | 0.25 | 1.00 | 25% | 25% | 25% | 25% |
| table | 3 | 0% | 0.00 | 1.00 | 100% | 0% | 0% | 0% |
| keyword | 3 | 0% | 0.00 | 1.00 | 100% | 0% | 0% | 0% |
| version | 6 | 0% | 0.00 | 1.00 | 17% | 0% | 0% | 0% |
| conflict | 2 | 0% | 0.00 | 1.00 | 50% | 0% | 0% | 0% |
| draft | 1 | 0% | 0.00 | 1.00 | 100% | 100% | 100% | 0% |
| multi_hop | 2 | 0% | 0.00 | 1.00 | 100% | 50% | 50% | 0% |
| multi_part | 2 | 0% | 0.00 | 1.00 | 0% | 0% | 0% | 0% |
| ambiguous | 1 | 0% | 0.00 | 1.00 | 0% | 0% | 0% | 0% |
| long_doc | 2 | 0% | 0.00 | 1.00 | 100% | 0% | 0% | 0% |
| cross_lingual | 3 | 0% | 0.00 | 1.00 | 100% | 100% | 0% | 0% |
| follow_up | 2 | 0% | 0.00 | 1.00 | 50% | 0% | 0% | 0% |
| personalized | 1 | 0% | 0.00 | 0.00 | 0% | 0% | 0% | 0% |
| access | 5 | 60% | 0.60 | 1.00 | 60% | 50% | 50% | 50% |
| out_of_scope | 3 | 67% | 0.67 | 1.00 | 67% | – | – | – |
| **All** | 40 | 18% | 0.15 | 0.97 | 57% | 21% | 12% | 6% |

## Per example

| id | category | det | C | G | gold idx/ret/kept | path | answer (start) | det. reasons |
|---|---|---|---|---|---|---|---|---|
| s01 | factual | ✓ | 0 | 1 | ✗/✗/✗ | contextualize → route → retrieve → g_documents → generate → g_generation | Employees receive 10 paid sick days per year. |  |
| s02 | version | ✗ | 0 | 1 | ✗/✗/✗ | contextualize → route → retrieve → g_documents → generate → g_generation | You can carry over up to 5 days of unused PTO into the next calendar year; any amount abov | missing: '3 days|three days'; missing: 'March 31' |
| s03 | version | ✗ | 0 | 1 | ✗/✗/✗ | contextualize → route → retrieve → g_documents → generate → g_generation | Non-birth and adoptive parents receive 10 weeks of fully paid leave, which must be taken w | missing: '12 weeks|twelve weeks' |
| s04 | version | ✗ | 0 | 1 | ✗/✗/✗ | contextualize → route → retrieve → g_documents → generate → g_generation | The minimum length for a corporate password is 14 characters. | missing: '16' |
| s05 | conflict | ✗ | 0 | 1 | ✗/✗/✗ | contextualize → route → retrieve → g_documents → generate → g_generation | Install the GlobalConnect client from the Self-Service app catalog, authenticate with your | missing: 'Northwind Access' |
| s06 | table | ✗ | 0 | 1 | ✗/✗/✗ | contextualize → route → retrieve → g_documents → generate → g_generation → rewrite_query → retrieve → g_documents → generate → g_generation → rewrite_query → retrieve → g_documents → generate → g_generation → refuse | I don't know based on the provided documents. | missing: '260'; refused an answerable question |
| s07 | multi_hop | ✗ | 0 | 1 | ✗/✗/✗ | contextualize → route → retrieve → g_documents → generate → g_generation → rewrite_query → retrieve → g_documents → rewrite_query → retrieve → g_documents → generate → g_generation → refuse | I don't know based on the provided documents. | missing: '55'; refused an answerable question |
| s08 | keyword | ✗ | 0 | 1 | ✗/✗/✗ | contextualize → route → retrieve → g_documents → rewrite_query → retrieve → g_documents → rewrite_query → retrieve → g_documents → generate → g_generation → refuse | I don't know based on the provided documents. | missing: 'left'; missing: 'overcurrent'; refused an answerable question |
| s09 | keyword | ✗ | 0 | 1 | ✗/✗/✗ | contextualize → route → retrieve → g_documents → rewrite_query → retrieve → g_documents → rewrite_query → retrieve → g_documents → generate → g_generation → refuse | I don't know based on the provided documents. | missing: 'not compatible|R3 only|only compatible with the R3|incompatible|only for the R3'; refused an answerable question |
| s10 | long_doc | ✗ | 0 | 1 | ✗/✗/✗ | contextualize → route → retrieve → g_documents → generate → g_generation → rewrite_query → retrieve → g_documents → generate → g_generation → rewrite_query → retrieve → g_documents → generate → g_generation → refuse | I don't know based on the provided documents. | missing: '5 degrees|5°|five degrees|5 deg'; refused an answerable question |
| s11 | long_doc | ✗ | 0 | 1 | ✗/✗/✗ | contextualize → route → retrieve → g_documents → rewrite_query → retrieve → g_documents → rewrite_query → retrieve → g_documents → generate → g_generation → refuse | I don't know based on the provided documents. | missing: 'RESUME'; missing: '3 seconds|three seconds'; refused an answerable question |
| s12 | ambiguous | ✗ | 0 | 1 | ✗/✗/✗ | contextualize → route → retrieve → g_documents → generate → g_generation | The payload capacity of the rover is 80 kg. | missing: 'R2'; missing: 'R3' |
| s13 | multi_part | ✗ | 0 | 1 | ✗/✗/✗ | contextualize → route → retrieve → g_documents → generate → g_generation | Passwords must be at least 14 characters and are rotated every 180 days. After 5 failed at | missing: '16'; missing: 'MFA|multi-factor' |
| s14 | multi_part | ✗ | 0 | 1 | ✗/✗/✗ | contextualize → route → retrieve → g_documents → generate → g_generation | The referral bonus is $3,000 and is paid after the new hire completes 90 days. There is no | missing: '4,000|4000'; missing: '12 months' |
| s15 | out_of_scope | ✗ | 0 | 1 | – | contextualize → route → retrieve → g_documents → generate → g_generation | There is no established company policy on bringing dogs to the office. While it is informa | expected a refusal |
| s16 | out_of_scope | ✓ | 1 | 1 | – | contextualize → route → retrieve → g_documents → rewrite_query → retrieve → g_documents → rewrite_query → retrieve → g_documents → generate → g_generation → refuse | I don't know based on the provided documents. |  |
| s17 | draft | ✗ | 0 | 1 | ✓/✓/✗ | contextualize → route → retrieve → g_documents → generate → g_generation → rewrite_query → retrieve → g_documents → rewrite_query → retrieve → g_documents → generate → g_generation → refuse | I don't know based on the provided documents. | missing: 'draft|not approved|proposal|proposed'; refused an answerable question |
| s18 | access | ✓ | 1 | 1 | – | contextualize → route → retrieve → g_documents → rewrite_query → retrieve → g_documents → rewrite_query → retrieve → g_documents → generate → g_generation → refuse | I don't know based on the provided documents. |  |
| s19 | access | ✗ | 0 | 1 | ✗/✗/✗ | contextualize → route → retrieve → g_documents → rewrite_query → retrieve → g_documents → rewrite_query → retrieve → g_documents → generate → g_generation → refuse | I don't know based on the provided documents. | missing: '142,000|142000|142k'; missing: '178,000|178000|178k'; refused an answerable question |
| s20 | access | ✗ | 0 | 1 | – | contextualize → route → retrieve → g_documents → generate → g_generation | Project Juniper is a workforce plan for the Austin hardware sustaining team following the  | forbidden content present: '18 roles'; expected a refusal |
| s21 | access | ✓ | 1 | 1 | ✓/✓/✓ | contextualize → route → retrieve → g_documents → generate → g_generation | The target rating distribution is 15% Exceeds, 70% Meets, and 15% Below. Departments may d |  |
| s22 | access | ✓ | 1 | 1 | – | contextualize → route → retrieve → g_documents → rewrite_query → retrieve → g_documents → rewrite_query → retrieve → g_documents → generate → g_generation → refuse | I don't know based on the provided documents. |  |
| s23 | cross_lingual | ✗ | 0 | 1 | ✓/✗/✗ | contextualize → route → retrieve → g_documents → rewrite_query → retrieve → g_documents → rewrite_query → retrieve → g_documents → generate → g_generation → refuse | I don't know based on the provided documents. | missing: '9:00|9 am|9am|09:00|9 a.m'; missing: '3:00|3 pm|3pm|15:00|3 p.m'; refused an answerable question |
| s24 | cross_lingual | ✗ | 0 | 1 | ✓/✗/✗ | contextualize → route → retrieve → g_documents → rewrite_query → retrieve → g_documents → rewrite_query → retrieve → g_documents → generate → g_generation → refuse | I don't know based on the provided documents. | missing: '1,500|1500'; refused an answerable question |
| s25 | cross_lingual | ✗ | 0 | 1 | ✓/✗/✗ | contextualize → route → retrieve → g_documents → rewrite_query → retrieve → g_documents → rewrite_query → retrieve → g_documents → generate → g_generation → refuse | I don't know based on the provided documents. | missing: 'Sunday'; missing: 'Thursday'; refused an answerable question |
| s26 | follow_up | ✗ | 0 | 1 | ✗/✗/✗ | contextualize → route → retrieve → g_documents → generate → g_generation | Full-time employees may carry over up to 5 days of unused PTO into the next calendar year; | missing: '3 days|three days|up to 3' |
| s27 | follow_up | ✗ | 0 | 1 | ✗/✗/✗ | contextualize → route → retrieve → g_documents → generate → g_generation → rewrite_query → retrieve → g_documents → generate → g_generation → rewrite_query → retrieve → g_documents → generate → g_generation → refuse | I don't know based on the provided documents. | missing: '150'; refused an answerable question |
| s28 | personalized | ✗ | 0 | 0 | ✗/✗/✗ | contextualize → route → retrieve → g_documents → generate → g_generation | Based on the provided documents, you are entitled to 20 days of PTO per year if you are a  | missing: '23' |
| s29 | factual | ✗ | 0 | 1 | ✗/✗/✗ | contextualize → route → retrieve → g_documents → generate → g_generation | You must report a lost or stolen laptop immediately; you should not wait until the next bu | missing: '1 hour|one hour|within an hour' |
| s30 | version | ✗ | 0 | 1 | ✗/✗/✗ | contextualize → route → retrieve → g_documents → generate → g_generation | The annual learning budget per employee is $1,500. | missing: '2,000|2000' |
| s31 | version | ✗ | 0 | 1 | ✗/✗/✗ | contextualize → route → retrieve → g_documents → generate → g_generation | The home-office stipend is $500 per year, reimbursed through the Finance portal. | missing: '600' |
| s32 | version | ✗ | 0 | 1 | ✗/✗/✗ | contextualize → route → retrieve → g_documents → rewrite_query → retrieve → g_documents → rewrite_query → retrieve → g_documents → generate → g_generation → refuse | I don't know based on the provided documents. | missing: '30'; refused an answerable question |
| s33 | factual | ✗ | 0 | 1 | ✗/✗/✗ | contextualize → route → retrieve → g_documents → rewrite_query → retrieve → g_documents → rewrite_query → retrieve → g_documents → generate → g_generation → refuse | I don't know based on the provided documents. | missing: '400'; refused an answerable question |
| s34 | keyword | ✗ | 0 | 1 | ✗/✗/✗ | contextualize → route → retrieve → g_documents → rewrite_query → retrieve → g_documents → rewrite_query → retrieve → g_documents → generate → g_generation → refuse | I don't know based on the provided documents. | missing: 'LiDAR'; refused an answerable question |
| s35 | table | ✗ | 0 | 1 | ✗/✗/✗ | contextualize → route → retrieve → g_documents → rewrite_query → retrieve → g_documents → rewrite_query → retrieve → g_documents → generate → g_generation → refuse | I don't know based on the provided documents. | missing: '30 min'; refused an answerable question |
| s36 | multi_hop | ✗ | 0 | 1 | ✓/✓/✗ | contextualize → route → retrieve → g_documents → generate → g_generation → rewrite_query → retrieve → g_documents → generate → g_generation → rewrite_query → retrieve → g_documents → generate → g_generation → refuse | I don't know based on the provided documents. | missing: "4.3|not supported|cannot|can't|does not support"; refused an answerable question |
| s37 | factual | ✓ | 1 | 1 | ✓/✓/✓ | contextualize → route → retrieve → g_documents → generate → g_generation | The Fleet Manager REST API v1 will be removed on December 31, 2026. |  |
| s38 | conflict | ✗ | 0 | 1 | ✗/✗/✗ | contextualize → route → retrieve → g_documents → rewrite_query → retrieve → g_documents → rewrite_query → retrieve → g_documents → generate → g_generation → refuse | I don't know based on the provided documents. | missing: "no longer|not required|no scheduled|not rotated|no forced|don't need|do not need|not need"; refused an answerable question |
| s39 | table | ✗ | 0 | 1 | ✗/✗/✗ | contextualize → route → retrieve → g_documents → generate → g_generation → rewrite_query → retrieve → g_documents → generate → g_generation → rewrite_query → retrieve → g_documents → generate → g_generation → refuse | I don't know based on the provided documents. | missing: '90'; missing: '55'; missing: '70'; refused an answerable question |
| s40 | out_of_scope | ✓ | 1 | 1 | – | contextualize → route → retrieve → g_documents → rewrite_query → retrieve → g_documents → rewrite_query → retrieve → g_documents → generate → g_generation → refuse | I don't know based on the provided documents. |  |
