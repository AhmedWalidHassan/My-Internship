## Task 4: Naive RAG pipeline

### What I built

- `store.as_retriever(search_kwargs={"k": k})`: wraps the same similarity search
  from Task 3 in the standard Runnable interface (question string in, list of
  `Document`s out), so it can be used with `|` like everything else.
- `format_docs`: turns the retrieved `Document`s into one context string, with
  each chunk prefixed by its source file name (`[employee_handbook.md] ...`).
  The LLM can't read `Document` objects, and the source tags are what let it
  cite where an answer came from.
- The RAG chain:

```python
{"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt | llm | StrOutputParser()
```

### How the chain works

The dict at the start becomes a `RunnableParallel`: every key receives the same
input (the question string) and the results are collected into a dict.

- `"context"`: the retriever fetches chunks, and `format_docs` joins them into text.
- `"question"`: `RunnablePassthrough()` passes the question through unchanged.

That dict feeds the prompt, whose `{context}` and `{question}` slots must match
the dict keys. After that it's the same `prompt | llm | parser` chain as Task 1.
In other words, RAG is the Task 1 chain with a retrieval step added at the front.

### Results (k=4, qwen3.5:4b, 10 chunks in the corpus)

| Question | Answer | Sources listed |
|----------|--------|----------------|
| How many sick days do I get per year? | 10 paid sick days per year | `employee_handbook.md` |
| What is the max payload of the Warehouse Rover R2? | 80 kg | `product_specs.md` |
| What is the CEO's home address? | "I don't know based on the provided documents." | `it_faq.md`, `employee_handbook.md`, `product_specs.md` |

### Observations

- **Grounded answers work.** The first two questions were answered with a
  source file.
- **The "I don't know" behavior works.** For a question that isn't in the
  documents, the model refused correctly instead of making something up.
- **But it still listed sources for the refusal.** The system prompt says to
  list the source files used after the answer. The model followed that
  literally even though it used nothing, so the output claims three sources
  for an answer of "I don't know". That's a prompt weakness, not a retrieval
  problem. A fix is to say "If the answer is not in the context, reply only
  with: 'I don't know...' and do not list sources."
- **Inconsistent formatting.** The sources appeared as plain text in one
  answer and as bold bullets with square brackets in the others. The model is
  copying the `[source]` tag style from the context. A stricter format
  instruction in the prompt would make the output consistent.
- **The corpus is too small to stress retrieval.** With k=4 out of 10 chunks,
  40% of the whole corpus goes into every prompt, so retrieval mistakes are
  easy to hide. This would look different with thousands of chunks.
