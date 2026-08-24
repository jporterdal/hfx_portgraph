Corpus PDFs are collected (Port of Halifax) and parsed by `parse.py` using the Docling library (https://github.com/docling-project/docling) into multiple MD files with associated "provenance" (e.g., page number) information within JSON files.

These markdown files are then parsed using `chunk.py` into parent/child chunks of sizes deemed heuristically appropriate, stored in JSONL files. Page source information (for future citations) is included.

These chunks are processed by `rag.py` which calculates an embedding for each chunk and stores it in a local Chroma DB (embedding-optimized DB). The embeddings are calculated using ollama with model `nomic-embed-text` (defined in `paths.py`).

At this point, questions can be asked using `ask()` within `rag.py`. A string question/prompt is provided and converted to an embedding using the same process with ollama that was used to calculate the embeddings of the document chunks. The Chroma DB is then queried using the embedding and entries with nearby embeddings are returned. The helper function `retrieve()` is responsible for querying the DB and by default will return the best 6 results.

The returned results are formatted and included alongside the user's actual question as "Evidence", then provided to the ollama chat model (distinct from the embedding model) as one large prompt including each child/parent chunk pair that matched on the question based on embedding distance. The response received from the chat model is given back to the user.

