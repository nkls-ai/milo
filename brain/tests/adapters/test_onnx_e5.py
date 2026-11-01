import numpy as np
import pytest

from milo.adapters.embed.onnx_e5 import OnnxE5, _pool


def test_pool_excludes_padding_and_normalizes():
    hidden = np.array([[[3, 0], [0, 4], [900, 900]], [[0, 0], [0, 0], [0, 0]]], dtype=np.float32)
    result = _pool(hidden, np.array([[1, 1, 0], [1, 0, 0]]))
    np.testing.assert_allclose(result, [[.6, .8], [0, 0]])
    assert result.dtype == np.float32


def test_empty_does_not_load_models():
    model = OnnxE5()
    assert model.embed([]).shape == (0, 384)
    assert model._session is None


@pytest.mark.parametrize("threads", [0, 33, -1, True, 2.5, "2"])
def test_bounded_threads(threads):
    with pytest.raises(ValueError):
        OnnxE5(threads=threads)


def test_key_changes_when_model_revision_changes():
    assert OnnxE5(revision="one").key != OnnxE5(revision="two").key


def test_batching_prefix_mask_and_input_contract():
    from types import SimpleNamespace

    class Tokenizer:
        texts = []
        def encode_batch(self, texts):
            self.texts.extend(texts)
            return [SimpleNamespace(ids=[i + 1, 1], attention_mask=[1, 0]) for i in range(len(texts))]

    class Session:
        sizes = []
        def get_inputs(self):
            return [SimpleNamespace(name=name) for name in ("input_ids", "attention_mask")]
        def run(self, outputs, inputs):
            assert set(inputs) == {"input_ids", "attention_mask"}
            assert inputs["input_ids"].dtype == np.int64
            self.sizes.append(len(inputs["input_ids"]))
            result = np.ones((*inputs["input_ids"].shape, 384), dtype=np.float32)
            result[:, 1, :] = 1000
            return [result]

    model = OnnxE5()
    model._session, model._tokenizer = Session(), Tokenizer()
    result = model.embed([str(i) for i in range(35)], query=True)
    assert result.shape == (35, 384)
    np.testing.assert_allclose(np.linalg.norm(result, axis=1), 1, atol=1e-6)
    assert model._session.sizes == [32, 3]
    assert model._tokenizer.texts == [f"query: {i}" for i in range(35)]
    model.embed(["fact"])
    assert model._tokenizer.texts[-1] == "passage: fact"
