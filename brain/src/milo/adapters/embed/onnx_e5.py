"""The Mac's multilingual e5 semantic memory model, running on a portable CPU runtime."""
from __future__ import annotations

import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from milo.core.registry import EMBEDDERS, AdapterContext, ConfigError, options_from

MAX_TOKENS = 256
BATCH = 32


@dataclass(frozen=True)
class OnnxE5Options:
    model: str = "Xenova/multilingual-e5-small"
    revision: str = "main"
    filename: str = "onnx/model_quantized.onnx"
    threads: int = 2


class OnnxE5:
    name = "onnx_e5"
    dimensions = 384
    relevant_margin = 0.04

    def __init__(self, model: str = OnnxE5Options.model, *, revision: str = "main",
                 filename: str = OnnxE5Options.filename, threads: int = 2, path: Path | None = None):
        if type(threads) is not int or not 1 <= threads <= 32:
            raise ValueError("memory.onnx_e5.threads must be between 1 and 32")
        if any(not isinstance(value, str) or not value.strip() for value in (model, revision, filename)):
            raise ValueError("memory.onnx_e5 model, revision and filename must be nonempty strings")
        if Path(filename).is_absolute() or ".." in Path(filename).parts:
            raise ValueError("memory.onnx_e5.filename must stay inside the model directory")
        self.model, self.revision, self.filename = model, revision, filename
        self.threads, self._path = threads, path
        self._session = self._tokenizer = None
        self._lock = threading.Lock()

    @property
    def key(self) -> str:
        return f"onnx_e5:{self.model}:{self.revision}:{self.filename}"

    def warm(self) -> None:
        self.embed(["warm up"], query=True)

    def _load(self) -> None:
        if self._session is not None:
            return
        import onnxruntime as ort
        from tokenizers import Tokenizer

        path = self._path
        if path is None:
            from huggingface_hub import snapshot_download
            path = Path(snapshot_download(self.model, revision=self.revision,
                        allow_patterns=["tokenizer.json", self.filename]))
        tokenizer = Tokenizer.from_file(str(path / "tokenizer.json"))
        tokenizer.enable_truncation(max_length=MAX_TOKENS)
        tokenizer.enable_padding(pad_id=1, pad_token="<pad>")
        options = ort.SessionOptions()
        options.intra_op_num_threads = self.threads
        options.inter_op_num_threads = 1
        session = ort.InferenceSession(str(path / self.filename), sess_options=options,
                                      providers=["CPUExecutionProvider"])
        self._tokenizer, self._session = tokenizer, session

    def embed(self, texts: Sequence[str], *, query: bool = False) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimensions), dtype=np.float32)
        with self._lock:
            self._load()
            prefix = "query: " if query else "passage: "
            rows = []
            names = {item.name for item in self._session.get_inputs()}
            for start in range(0, len(texts), BATCH):
                encoded = self._tokenizer.encode_batch([prefix + t for t in texts[start:start + BATCH]])
                ids = np.asarray([e.ids for e in encoded], dtype=np.int64)
                mask = np.asarray([e.attention_mask for e in encoded], dtype=np.int64)
                inputs = {"input_ids": ids, "attention_mask": mask,
                          "token_type_ids": np.zeros_like(ids)}
                hidden = self._session.run(None, {k: v for k, v in inputs.items() if k in names})[0]
                if hidden.shape != (*ids.shape, self.dimensions):
                    raise ValueError("memory.onnx_e5 requires a 384-dimensional token encoder")
                rows.append(_pool(hidden, mask))
            return np.concatenate(rows)


def _pool(hidden: np.ndarray, mask: np.ndarray) -> np.ndarray:
    weights = mask[..., None].astype(np.float32)
    pooled = (hidden.astype(np.float32) * weights).sum(axis=1) / np.maximum(weights.sum(axis=1), 1)
    return pooled / np.maximum(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-9)


@EMBEDDERS.register("onnx_e5")
def _onnx_e5(options: Mapping[str, Any], ctx: AdapterContext) -> OnnxE5:
    try:
        return OnnxE5(**vars(options_from(OnnxE5Options, options, "memory.onnx_e5")))
    except ValueError as error:
        raise ConfigError(str(error)) from error
