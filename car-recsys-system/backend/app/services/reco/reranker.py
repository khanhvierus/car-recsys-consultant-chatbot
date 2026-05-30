"""Stage 3 — re-ranking. Maximal Marginal Relevance for diversity + hard caps.

The old engine could return ten near-identical cars (same model, same brand).
MMR trades a little relevance for variety:

    mmr = lambda · relevance  -  (1 - lambda) · max_similarity_to_already_picked

Plus hard caps: at most N per brand and per car model in the final list.
"""

from __future__ import annotations

import logging
from collections import Counter

from .config import RecoConfig
from .features import Candidate

log = logging.getLogger(__name__)


class MMRReranker:
    def __init__(self, config: RecoConfig):
        self.lam = config.mmr_lambda
        self.max_per_brand = config.max_per_brand
        self.max_per_model = config.max_per_model

    def rerank(self, ranked: list[Candidate], top_k: int) -> list[Candidate]:
        """Greedily pick `top_k` candidates balancing relevance and diversity.

        `ranked` must already be sorted by rank_score desc (the ranker's output).
        """
        if not ranked:
            return []

        # Relevance normalized to [0, 1] for a stable MMR trade-off.
        hi = max(c.rank_score for c in ranked) or 1.0
        rel = {c.vehicle_id: c.rank_score / hi for c in ranked}

        selected: list[Candidate] = []
        brand_count: Counter[str] = Counter()
        model_count: Counter[str] = Counter()
        pool = list(ranked)

        while pool and len(selected) < top_k:
            best: Candidate | None = None
            best_mmr = float("-inf")
            for c in pool:
                # Hard diversity caps.
                if c.brand and brand_count[c.brand] >= self.max_per_brand:
                    continue
                if c.car_model and model_count[c.car_model] >= self.max_per_model:
                    continue
                sim = self._max_similarity(c, selected)
                mmr = self.lam * rel[c.vehicle_id] - (1 - self.lam) * sim
                if mmr > best_mmr:
                    best_mmr, best = mmr, c

            if best is None:
                # Every remaining candidate hit a cap — relax caps to fill top_k.
                pool_relaxed = [c for c in pool if c not in selected]
                if not pool_relaxed:
                    break
                best = max(pool_relaxed, key=lambda c: rel[c.vehicle_id])

            selected.append(best)
            pool.remove(best)
            if best.brand:
                brand_count[best.brand] += 1
            if best.car_model:
                model_count[best.car_model] += 1

        return selected

    @staticmethod
    def _max_similarity(cand: Candidate, selected: list[Candidate]) -> float:
        """Cheap content-based similarity to the already-picked set: shares
        brand (0.5) and/or model (0.5). No embeddings needed at this stage."""
        if not selected:
            return 0.0
        best = 0.0
        for s in selected:
            sim = 0.0
            if cand.brand and cand.brand == s.brand:
                sim += 0.5
            if cand.car_model and cand.car_model == s.car_model:
                sim += 0.5
            best = max(best, sim)
        return best
