"""vLLM Semantic Router's d3-lite: a 0.85B decision model on the Qwen3.5 backbone, run with PyTorch (ADR 0040).

It reads a text and a question and scores every answer in one forward pass, generating nothing: a yes-or-no as the
probability of yes, a choice as a probability for each option. It reads German, English, French, Spanish and many
more; on the Mac's GPU four questions about a sentence take about a second, an email sorted into folders a third of
one. About 1.7 GB on disk and in memory, downloaded from Hugging Face on first use.

The repository's own runtime (`trust_remote_code`) does the work, at a pinned commit: new code there doesn't run
here until the revision below changes. torch and transformers come with the omnivoice extra.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from milo.core.decide import Answer, Choice, Question, YesNo
from milo.core.registry import DECIDERS, AdapterContext, options_from

log = logging.getLogger("milo.decide")


@dataclass(frozen=True)
class D3Options:
    model: str = "vllm-sr/d3-lite"
    revision: str = "9c10703193afc7c7d28c88201c0364bfbbf58320"
    """A commit, so the runtime code the model brings is the one checked here."""
    device: str = "auto"
    """"auto" (CUDA, else the Mac's GPU, else the CPU), or a torch device name. On a CPU a question takes seconds."""


class D3:
    """Decider. Blocking; call it from one thread (services/decisions.py)."""

    name = "d3"

    def __init__(self, model: str = D3Options.model, *, revision: str = D3Options.revision, device: str = "auto"):
        self.model = model
        self.revision = revision
        self.device = device
        self._net: Any = None
        self._loading = threading.Lock()

    def warm(self) -> None:
        self.decide("warm up", {"q": YesNo("Is this a greeting?")})

    def decide(self, text: str, questions: Mapping[str, Question]) -> dict[str, Answer | None]:
        # All questions in one call. One per call was a fifth faster but read two sentences of the eval otherwise
        # ("ich brauche Streichhölzer" as work), and the questions were tuned together.
        answers = self._load().system_one(state=text, questions={k: _wire(q) for k, q in questions.items()})["answers"]
        return {k: _answer(answers.get(k)) for k in questions}

    def _load(self) -> Any:
        with self._loading:
            if self._net is None:
                from transformers import AutoModel

                device = _device(self.device)
                self._net = AutoModel.from_pretrained(self.model, revision=self.revision, trust_remote_code=True,
                                                      device=device)
                log.info("decision model %s on %s", self.model, device)
            return self._net


def _wire(q: Question) -> dict:
    if isinstance(q, Choice):
        return {"type": "choice", "instructions": q.question, "criteria": dict(q.options)}
    return {"type": "noul", "instructions": q.question}


def _answer(a: Any) -> Answer | None:
    if not isinstance(a, dict) or "error" in a:
        if isinstance(a, dict):
            log.info("decision model couldn't answer: %s", a.get("message") or a.get("error"))
        return None
    if a.get("type") == "noul":
        return float(a["noul"])
    return {str(k): float(v) for k, v in a.get("probabilities", {}).items()}


def _device(name: str) -> str:
    if name != "auto":
        return name
    import torch

    if torch.cuda.is_available():
        return "cuda:0"
    return "mps" if torch.backends.mps.is_available() else "cpu"


@DECIDERS.register("d3")
def _d3(options: Mapping[str, Any], ctx: AdapterContext) -> D3:
    o = options_from(D3Options, options, "decide.d3")
    return D3(o.model, revision=o.revision, device=o.device)


@DECIDERS.register("none")
def _none(options: Mapping[str, Any], ctx: AdapterContext) -> None:
    return None
