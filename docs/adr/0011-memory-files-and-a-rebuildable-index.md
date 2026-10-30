# 11. Memory lives in append-only files; the search index is a cache

Date: 2026-10-30. Status: accepted. Builds [the memory design](../design/memory.md).

## Context

Milo should remember episodes and facts for years, survive crashes without losing any, let the user read and fix what he knows, and later sync between devices end-to-end encrypted. Each turn needs a relevant slice of that memory in well under 50 ms, without calling a model, on a 16 GB Mac where Whisper and OmniVoice already hold about 4 GB.

## Decision

- **The truth is append-only JSON lines.** `memory/episodes/YYYY-MM.jsonl` and `memory/facts.jsonl`, one change per line, never rewritten. An edit appends a new version (a fact with `replaces`, an episode with the same id); forgetting appends a marker. Readers skip a half-written last line, and the next append starts on a fresh line, so a crash mid-write loses at most that line. Facts are fsynced; files are readable by the user only.
- **The index is a cache.** `state/memory.sqlite` holds FTS5 for words and the vectors, and remembers how far into each log it has read (by size and mtime), so catching up is cheap. Delete it, damage it or change the embedder and it is built again from the logs; nothing in it is the only copy.
- **Vectors are searched in NumPy.** The vectors live in SQLite rows and are loaded into a matrix at start. sqlite-vec was the first choice and still works (`vectors="sqlite-vec"`), but over 6,600 items its scan took 33 ms median against 7 ms for the matrix.
- **The embedder is multilingual-e5-small in MLX,** on its own thread, quantized to 138 MB. Measured on the M3, under heavy load from other agents (load average 14 to 42):

  | Model | Memory | Bilingual check (top 1 of 20) | Per query |
  |---|---|---|---|
  | multilingual-e5-small, fp32 (mlx-embeddings) | 449 MB | 18 | 10 to 50 ms |
  | **multilingual-e5-small, our MLX code, fp16, 8-bit word table** | **138 MB** | **18** | **7.8 ms median, 10.7 ms p95; batch of 64 in 119 ms** |
  | embeddinggemma-300m, 4-bit | 167 MB | 20 | 140 to 170 ms |
  | Qwen3-Embedding-0.6B, 4-bit | 320 MB | 20 | 113 to 294 ms |

  Our code matches the reference model's vectors (cosine 1.0000). e5 is the only one fast enough to embed every turn without the user noticing; the larger two are slightly better at matching across German and English. `[memory] embedder = "hash"` is a no-model fallback for a Mac without room.
- **Consolidation is one worker call per day,** at night, on power, while the user is away, capped by `consolidate_calls_per_day`. It sees at most 150 of the day's trusted episodes and 400 facts.

## Consequences

- Plain files mean sync later can copy log lines between devices, encrypted, and each device builds its own index.
- Logs grow forever: about 50 episodes a day is roughly 5 MB a year of JSON, plus 28 MB of vectors in the index. Old months could be compacted later, since each month is its own file.
- The first start after an update downloads e5 once (470 MB from Hugging Face, of which 138 MB stays in memory). Until it is ready, turns go without recall.
- Cross-language matching is e5-small's weak spot: a German compound like "Zahnarzttermin" doesn't find an English episode about the dentist. A larger embedder can replace it through `[memory] embedder` once there is memory to spare; the index rebuilds itself.
