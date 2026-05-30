"""Stage 2 — ranking. A transparent weighted-linear scorer.

score = Σ weight_i · feature_i   (weights from reco_config.yaml)

Chosen over a black-box model so every recommendation is explainable in the
thesis: you can point at which signal drove a card up the list. Swappable for
a LightGBM ranker later behind the same `score()` interface.
"""

from __future__ import annotations

import logging
from typing import Iterable

from .config import RecoConfig
from .features import Candidate

log = logging.getLogger(__name__)


class WeightedLinearRanker:
    def __init__(self, config: RecoConfig):
        self.weights = config.ranker_weights

    def score(self, candidates: Iterable[Candidate]) -> list[Candidate]:
        """Assign rank_score to each candidate and return them sorted desc."""
        scored: list[Candidate] = []
        for c in candidates:
            feats = c.feature_dict()
            c.rank_score = sum(
                self.weights.get(name, 0.0) * value
                for name, value in feats.items()
            )
            scored.append(c)
        scored.sort(key=lambda c: c.rank_score, reverse=True)
        return scored

    def explain(self, candidate: Candidate) -> dict[str, float]:
        """Per-feature contribution to a candidate's score (for debugging / UI)."""
        return {
            name: round(self.weights.get(name, 0.0) * value, 4)
            for name, value in candidate.feature_dict().items()
        }
