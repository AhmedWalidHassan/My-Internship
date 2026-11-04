## Task 1: LangChain fundamentals (LCEL)

### What does the `|` operator actually do?

In LangChain, prompts, models and output parsers are all **Runnables**: objects
that share the same interface (`.invoke()`, `.batch()`, `.stream()`).
`Runnable` overloads Python's `|` operator (via `__or__`), so
`prompt | llm | parser` does not run anything. It builds a new Runnable, a
`RunnableSequence`, that remembers the steps in order.

When I call `chain.invoke(x)`, the sequence runs each step and passes the output
of one step in as the input of the next, like a Unix pipe:

```
{"topic": "vector databases"}          <- input dict
        |
   prompt   ->  ChatPromptValue (the formatted messages)
        |
    llm     ->  AIMessage (content + metadata)
        |
  parser    ->  str (just the text from the message)
```

Each step's output type must match what the next step accepts. That is why the
parser is needed: without `StrOutputParser()` the chain returns an `AIMessage`
object instead of a plain string.

Since the whole chain is itself a Runnable, it can be invoked, batched,
streamed, or piped into something bigger.

### How each chain works

1. **One-shot chain:** `ChatPromptTemplate` with a `{topic}` placeholder, then
   `llm`, then `StrOutputParser()`. The dict key passed to `.invoke()` must match
   the placeholder name exactly, or LangChain raises a `KeyError`.
2. **Structured chain:** `llm.with_structured_output(DocClassification)` gives
   back a validated Pydantic object instead of free text. The `Field(description=...)`
   strings are part of what the model sees, so better descriptions give better results.
3. **Summarize chain:** the same pattern as chain 1, with `{document}` filled
   from the file's text. Long documents would not fit in the model's context
   window, which is the problem chunking (Task 2) solves.

## Setup notes

- Running locally with **Ollama** and the `qwen3.5:4b` model, so no API key is needed.
- `.env` needs `LLM_PROVIDER=ollama`. The model name is set in `.env`.
