## Task 5: Conversational RAG with memory

### Problem

Follow-up questions like "Can I carry it over to next year?" don't make sense
on their own. If I embed that text directly, the vector search has no idea
what "it" is and retrieves poorly. A **history-aware retriever** first rewrites
the follow-up into a standalone question using the chat history, and only then
retrieves.

### What I built

I built the equivalent of the recommended pieces by hand in LCEL, using only
`langchain_core`:

1. **Contextualize:** a prompt with a `MessagesPlaceholder("chat_history")` and
   the new `{input}`. It tells the LLM to rewrite the question so it is
   understandable without the history (replace "it" and "that" with what they
   refer to) and **not** to answer it. On the first turn there is no history,
   so the rewrite is skipped to save an LLM call.
2. **Retrieve** on the rewritten (standalone) question, not on the raw input.
3. **Answer** with a second prompt containing the retrieved context, the chat
   history and the question. The system prompt says to use the history only to
   understand the question, never as a source of facts.
4. **Memory:** `RunnableWithMessageHistory` wraps the chain. On each call it
   looks up the history for the `session_id` in `config`, injects it as
   `chat_history`, runs the chain, then saves the new human and AI messages. A
   dict keyed by `session_id` gives each session its own history.

The chain uses `RunnablePassthrough.assign(...)` to add keys step by step
(`standalone`, then `docs`, then `context`, then `answer`). The keys
`input_messages_key="input"`, `history_messages_key="chat_history"` and
`output_messages_key="answer"` have to match the prompt variables and the
output dict, the same name-matching rule as `{topic}` in Task 1.

### Results

| Turn | Bot answer |
|------|-----------|
| How much PTO do I get? | 1.67 days per month (20 days per year), source `employee_handbook.md` |
| Can I carry it over to next year? | Up to 5 unused days carry into the next calendar year, anything above is forfeited on December 31, source `employee_handbook.md` |

The second question never mentions "PTO", yet the answer is correct and
mentions the 5-day cap. That means the rewrite step resolved "it" to PTO
before retrieval.

### Trade-offs I noticed

- **Two LLM calls per follow-up** (rewrite + answer) instead of one, so every
  follow-up is slower and costs more.
- **History grows without limit.** The full history is injected on every turn,
  so long conversations use more and more tokens. Trimming to the last N turns
  would cap the cost, but the bot would then forget older context, so a
  follow-up that depends on something said many turns ago would fail.
- **A small model (4B) rewrites less reliably.** It could answer the question
  instead of rewriting it, or add extra text. It worked here, but that is a
  risk to keep in mind.

### Things I noticed about the library

- `RunnableWithMessageHistory` and `InMemoryChatMessageHistory` print
  deprecation warnings: LangChain 1.x recommends LangGraph's built-in
  persistence for memory.
