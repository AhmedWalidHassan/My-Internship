# Task 6 NOTES

## Results (hit-rate on the 6 provided questions)
| strategy   | hit_rate |
|------------|----------|
| baseline   | 1.00     |
| mmr        | 1.00     |
| multiquery | 1.00     |
| hybrid     | 1.00     |

## Which strategy won?
None. All four strategies scored 1.00, so this benchmark cannot separate them.

## Hypothesis: why?
1. The corpus is tiny (4 files, roughly 15-20 chunks) and k=4, so each
   retriever returns about a quarter of the whole corpus. Finding the right
   file is easy even for plain similarity search.
2. hit_rate is lenient: it counts a hit if ANY of the 4 chunks comes from the
   gold file (file-level, not chunk-level), and it doesn't measure ranking.
3. The questions are paraphrased ("vacation days" vs "PTO"), but dense
   embeddings capture meaning, so the baseline already handles paraphrase.
   Hybrid's advantage (exact keywords like error codes) and multi-query's
   advantage (very different phrasing) don't show up with these questions.

## Next step
Addin harder questions like 
("time off carry rules?", "employee_handbook.md"),
("what does ISO 3691-4 mean?", "product_specs.md"),
("is alcohol reimbursable?", "hr_policies.md"),
("IP54 rating?", "product_specs.md")
gave me the same result because of the tiny corpus
