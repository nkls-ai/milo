"""multilingual-e5-small with MLX: German and English text to 384 numbers, on this Mac.

A plain BERT encoder (12 layers, 384 wide) written out here, so the only extra dependency is `tokenizers`.
Weights load as float16 and the 250k-word table as 8-bit, about 140 MB in memory. A short query takes a
few milliseconds. See docs/adr/0015-memory-files-and-a-rebuildable-index.md for how it was picked.
"""

from __future__ import annotations

import logging
import math
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from milo.core.registry import EMBEDDERS, AdapterContext, options_from

log = logging.getLogger(__name__)

FILES = ("config.json", "model.safetensors", "tokenizer.json")
MAX_TOKENS = 256
"""Episodes and facts are a sentence or two. Longer text is cut; its start says what it is about."""
BATCH = 32


@dataclass(frozen=True)
class MlxE5Options:
    model: str = "intfloat/multilingual-e5-small"
    revision: str = "main"
    device: str = "gpu"
    """"gpu" or "cpu". The GPU is faster for indexing many items; a single query is fast on either."""
    quantize_table: bool = True
    """Keep the word table (80% of the weights) in 8 bits: 140 MB instead of 230 MB, same results."""


class MlxE5:
    """Embedder. Blocking; call it from one thread (the memory executor)."""

    name = "mlx_e5"
    dimensions = 384
    relevant_margin = 0.04
    """e5 puts everything at 0.7-0.85, so cosine alone says little; a related memory stands 0.04-0.12 above the
    question's background, small talk's best match 0.00-0.04 (measured on the recall eval)."""

    def __init__(self, model: str = MlxE5Options.model, *, revision: str = "main", device: str = "gpu",
                 quantize_table: bool = True, path: Path | None = None):
        if device not in ("gpu", "cpu"):
            raise ValueError(f"device must be gpu or cpu, not {device!r}")
        self.model = model
        self.revision = revision
        self.device = device
        self.quantize_table = quantize_table
        self._path = path
        self._net: _Bert | None = None
        self._tokenizer = None
        self._loading = threading.Lock()

    @property
    def key(self) -> str:
        """Names the vector space: the index rebuilds its vectors when this changes."""
        return f"mlx_e5:{self.model}"

    def warm(self) -> None:
        self._load()
        self.embed(["warm up"], query=True)

    def embed(self, texts: Sequence[str], *, query: bool = False) -> np.ndarray:
        """Unit-length float32 rows. `query` marks search text, as e5 was trained with "query: "/"passage: "."""
        import mlx.core as mx

        if not texts:
            return np.zeros((0, self.dimensions), dtype=np.float32)
        net, tokenizer = self._load()
        prefix = "query: " if query else "passage: "
        encoded = [e.ids[:MAX_TOKENS] for e in tokenizer.encode_batch([prefix + t for t in texts])]
        order = sorted(range(len(encoded)), key=lambda i: len(encoded[i]))  # similar lengths pad less
        out = np.zeros((len(texts), self.dimensions), dtype=np.float32)
        with mx.stream(mx.gpu if self.device == "gpu" else mx.cpu):
            for start in range(0, len(order), BATCH):
                rows = order[start:start + BATCH]
                width = max(len(encoded[i]) for i in rows)
                ids = np.zeros((len(rows), width), dtype=np.int32)
                mask = np.zeros((len(rows), width), dtype=np.float32)
                for r, i in enumerate(rows):
                    ids[r, :len(encoded[i])] = encoded[i]
                    mask[r, :len(encoded[i])] = 1
                vectors = net(mx.array(ids), mx.array(mask))
                mx.eval(vectors)
                out[rows] = np.array(vectors.astype(mx.float32))
        return out

    def _load(self):
        with self._loading:
            if self._net is None:
                from tokenizers import Tokenizer

                path = self._path or _download(self.model, self.revision)
                log.info("loading %s", self.model)
                self._tokenizer = Tokenizer.from_file(str(path / "tokenizer.json"))
                self._tokenizer.no_padding()
                self._tokenizer.no_truncation()
                self._net = _Bert.load(path, quantize_table=self.quantize_table)
            return self._net, self._tokenizer


def _download(model: str, revision: str) -> Path:
    from huggingface_hub import snapshot_download

    return Path(snapshot_download(model, revision=revision, allow_patterns=list(FILES)))


class _Bert:
    """BERT forward pass with mean pooling, the way sentence-transformers runs e5."""

    def __init__(self, weights: dict, config: dict):
        self.w = weights
        self.layers = config["num_hidden_layers"]
        self.heads = config["num_attention_heads"]
        self.eps = config.get("layer_norm_eps", 1e-12)

    @classmethod
    def load(cls, path: Path, *, quantize_table: bool) -> _Bert:
        import json

        import mlx.core as mx

        config = json.loads((path / "config.json").read_text())
        raw = mx.load(str(path / "model.safetensors"))
        weights = {k: v.astype(mx.float16) for k, v in raw.items()
                   if not k.startswith("pooler.") and not k.endswith("position_ids")}
        table = weights.pop("embeddings.word_embeddings.weight")
        if quantize_table:
            weights["table"] = mx.quantize(table, group_size=64, bits=8)
        else:
            weights["table"] = (table,)
        mx.eval(weights)
        return cls(weights, config)

    def _lookup(self, ids):
        import mlx.core as mx

        table = self.w["table"]
        if len(table) == 1:
            return table[0][ids]
        q, scales, biases = table
        flat = ids.reshape(-1)
        rows = mx.dequantize(q[flat], scales[flat], biases[flat], group_size=64, bits=8)
        return rows.reshape(*ids.shape, -1)

    def __call__(self, ids, mask):
        import mlx.core as mx

        w, eps = self.w, self.eps
        n, width = ids.shape
        x = (self._lookup(ids) + w["embeddings.position_embeddings.weight"][:width]
             + w["embeddings.token_type_embeddings.weight"][0])
        x = _norm(x, w, "embeddings.LayerNorm", eps)
        head = x.shape[-1] // self.heads
        bias = ((1.0 - mask) * -1e4).astype(x.dtype)[:, None, None, :]
        for i in range(self.layers):
            p = f"encoder.layer.{i}."

            def split(t):
                return t.reshape(n, width, self.heads, head).transpose(0, 2, 1, 3)

            q = split(_linear(x, w, p + "attention.self.query"))
            k = split(_linear(x, w, p + "attention.self.key"))
            v = split(_linear(x, w, p + "attention.self.value"))
            a = mx.fast.scaled_dot_product_attention(q, k, v, scale=1 / math.sqrt(head), mask=bias)
            a = a.transpose(0, 2, 1, 3).reshape(n, width, -1)
            x = _norm(x + _linear(a, w, p + "attention.output.dense"), w, p + "attention.output.LayerNorm", eps)
            h = _linear(x, w, p + "intermediate.dense")
            h = h * 0.5 * (1 + mx.erf(h / math.sqrt(2)))  # exact GELU, as BERT
            x = _norm(x + _linear(h, w, p + "output.dense"), w, p + "output.LayerNorm", eps)
        m = mask.astype(mx.float32)[:, :, None]
        pooled = (x.astype(mx.float32) * m).sum(axis=1) / mx.maximum(m.sum(axis=1), 1)
        return pooled / mx.maximum(mx.linalg.norm(pooled, axis=1, keepdims=True), 1e-9)


def _linear(x, w, name):
    return x @ w[name + ".weight"].T + w[name + ".bias"]


def _norm(x, w, name, eps):
    import mlx.core as mx

    return mx.fast.layer_norm(x, w[name + ".weight"], w[name + ".bias"], eps)


@EMBEDDERS.register("mlx_e5")
def _mlx_e5(options: Mapping[str, Any], ctx: AdapterContext) -> MlxE5:
    o = options_from(MlxE5Options, options, "memory.mlx_e5")
    return MlxE5(o.model, revision=o.revision, device=o.device, quantize_table=o.quantize_table)
