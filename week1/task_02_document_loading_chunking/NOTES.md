## Task 2: Document loading & chunking

### Results

Loaded the 4 markdown files in `data/` (each between ~1,200 and ~1,700 characters)
with `TextLoader`, then split them with `RecursiveCharacterTextSplitter`
(overlap = chunk_size // 8):

| chunk_size | chunks |
|-----------:|-------:|
| 400        | 24     |
| 800        | 10     |
| 1500       | 7      |

Every chunk keeps `metadata["source"]` (the file path), because I used
`split_documents` rather than `split_text`. `split_text` works on plain strings
and would drop the metadata.

### Reflection

**1. What happened to the chunk count as chunk_size grew? Why?**

It went down (24 -> 10 -> 7). Each chunk can hold more text, so fewer chunks are
needed to cover the same documents. It is not exactly proportional, for two
reasons: the splitter cuts at natural boundaries (paragraphs, then lines, then
spaces) rather than at an exact character count, and every document needs at
least one chunk. At 1500, `hr_policies.md` (1,244 chars) stays whole while the
other three, which are slightly longer than 1,500 characters, each split in two:
3 x 2 + 1 = 7.

**2. If a policy answer spans two paragraphs, how does overlap help?**

`chunk_overlap` repeats the last part of one chunk at the start of the next. If
the answer sits across a chunk boundary, the overlap makes it likely that at
least one chunk contains the connecting text, so the retriever can find it and
the LLM sees it with enough context. Without overlap, a sentence cut at the
boundary is split into two halves, and neither half may match the question well.
The cost of overlap is duplicated text: a few more chunks and a bit more
embedding and storage.

**3. Which chunk size will retrieve best for these docs, and why?**

My hypothesis is that around 800 characters is a good fit. The documents are
short and organized into numbered sections with headings, and a section is
roughly one self-contained idea. 400 risks cutting a section in the middle,
losing the context that makes a sentence meaningful. 1500 is almost the size of
a whole document, so a retrieved chunk would carry a lot of unrelated text.

### What is `chunk_overlap` for, and when are large vs. small chunks better?

- **Overlap** keeps context across chunk boundaries (see question 2). Too much
  wastes space and creates near-duplicate results. None at all risks cutting
  ideas in half.
- **Small chunks** give more precise retrieval, because each chunk is about one
  narrow thing. They suit short factual questions ("how many PTO days?"). The
  risk is losing surrounding context.
- **Large chunks** keep more context together. They suit questions that need
  reasoning across several sentences or a whole section. The risk is noise: the
  answer is buried among irrelevant text, which can also dilute the embedding.