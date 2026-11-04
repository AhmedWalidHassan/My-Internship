## Task 3: Embeddings & vector stores (FAISS)

### What I built

- `FAISS.from_documents(chunks, embeddings)`: embeds every chunk (text to a
  vector that represents its meaning), stores the vectors in a FAISS index, and
  keeps the original `Document`s (text + `metadata["source"]`) next to them.
- `save_local(INDEX_DIR)`: writes `index.faiss` (the vectors) and `index.pkl`
  (the documents and metadata) to disk, so the corpus doesn't have to be
  re-embedded on every run.
- `FAISS.load_local(INDEX_DIR, embeddings, allow_dangerous_deserialization=True)`:
  reads the index back. It needs the **same embedding model** that built the
  index, because the query is embedded with it and compared against the stored
  vectors. Vectors from different models are not comparable.

### Setup notes

- The embeddings run locally through a small `sentence-transformers` model
  downloaded from HuggingFace on the first run.
  Model: `sentence-transformers/all-MiniLM-L6-v2` (384-dimensional vectors).
  It truncates input beyond 256 word pieces (tokens), roughly 1,000 characters
  of English, so a chunk much larger than that would be partly ignored when
  embedding. The 800-character chunks fit.
- The corpus is 10 chunks (chunk_size=800, overlap=100, same as Task 2).

### Retrieval observations (k=2)

| Query | 1st result | 2nd result |
|-------|-----------|------------|
| How much PTO do I get? | `employee_handbook.md`, the PTO section (correct) | `hr_policies.md`, performance reviews (not relevant) |
| What should I do if my laptop is stolen? | `it_faq.md`, the lost/stolen laptop Q&A (correct) | `it_faq.md`, the FAQ intro/accounts section (not relevant) |
| What is the payload capacity of the rover? | `product_specs.md`, overview of the Warehouse Rover R2 (right document) | `product_specs.md`, the Software section (not relevant) |

- The first result was in the right document every time, and for the PTO and
  laptop queries it contained the actual answer.
- The second result was weaker in all three cases. This is expected: vector
  search **always returns exactly k results**, whether or not they are
  relevant. With only 10 chunks in the corpus, the 2nd nearest chunk is
  just the "least bad" leftover.
