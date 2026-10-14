 # Task 4: Naive RAG Pipeline

A question-answering pipeline over Northwind Robotics' internal documents.
It retrieves relevant chunks, passes them to an LLM, and answers using only
that context, citing the source files.

## How it works

```
question → retriever (FAISS, top-k) → format_docs → prompt → LLM → answer
```

1. **Load and split** the `.md` documents into chunks (800 characters, 100 overlap).
2. **Embed and index** the chunks with FAISS.
3. **Retrieve** the top-k most similar chunks for each question.
4. **Generate** an answer using only the retrieved context, and list the sources.
5. If the answer is not in the context, the model replies:
   `I don't know based on the provided documents.`

## What I implemented

- `build_retriever`: returns `store.as_retriever(search_kwargs={"k": k})`
- `format_docs`: joins chunks as `[source_file] content`
- `build_rag_chain`: LCEL chain using `RunnableParallel`, `RunnablePassthrough`,
  the prompt, the LLM, and `StrOutputParser`

## How to run

From the `week1` folder:

```
pip install -r requirements.txt
python task_04_naive_rag/starter.py
```

An API key is required (set it as the course instructions say). Do not commit it.

## Results

| Question | Result |
|---|---|
| How many sick days do I get per year? | 10 days, source: employee_handbook.md |
| Max payload of the Warehouse Rover R2? | 80 kg, source: product_specs.md |
| What is the CEO's home address? | "I don't know based on the provided documents." |

## Known issue

For "Which robot is best for outdoor use?" the model correctly said it didn't
know (the docs only describe an indoor robot), but it still listed sources.
See `NOTES.md` for the analysis.

## Files

- `starter.py`: the pipeline
- `NOTES.md`: analysis of a failure case
