"""Recommendation engine configuration — loaded once from reco_config.yaml.

All tunables (interaction weights, time-decay lambda, ranker feature weights,
MMR diversity) live in the YAML so the engine has no magic numbers and the
thesis can cite a single config artifact.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).with_name("reco_config.yaml")

_DEFAULT_INTERACTION_WEIGHTS: dict[str, float] = {
    "view": 1.0, "click": 2.0, "compare": 3.0,
    "save": 4.0, "favorite": 4.0, "contact": 8.0, "inquiry": 8.0,
}
_DEFAULT_RANKER_WEIGHTS: dict[str, float] = {
    "cf_score": 3.0, "content_score": 1.5, "vector_score": 2.0,
    "popularity": 1.0, "price_fit": 1.0, "model_rating": 0.8, "recency": 0.5,
}


@dataclass(frozen=True, slots=True)
class CandidateConfig:
    collaborative_enabled: bool = True
    collaborative_user_history_limit: int = 50
    collaborative_neighbors_per_seed: int = 20
    content_enabled: bool = True
    content_limit: int = 150
    content_price_band_pct: float = 0.30
    vector_enabled: bool = True
    vector_limit: int = 100
    popularity_enabled: bool = True
    popularity_limit: int = 100


@dataclass(frozen=True, slots=True)
class RecoConfig:
    interaction_weights: dict[str, float] = field(
        default_factory=lambda: dict(_DEFAULT_INTERACTION_WEIGHTS))
    time_decay_lambda: float = 0.05
    ranker_weights: dict[str, float] = field(
        default_factory=lambda: dict(_DEFAULT_RANKER_WEIGHTS))
    mmr_lambda: float = 0.7
    max_per_brand: int = 3
    max_per_model: int = 2
    top_k: int = 20
    candidate_pool_size: int = 300
    candidates: CandidateConfig = field(default_factory=CandidateConfig)

    def interaction_weight(self, interaction_type: str) -> float:
        return self.interaction_weights.get(interaction_type, 1.0)


def _load_yaml() -> dict[str, Any]:
    try:
        import yaml
    except ImportError:
        log.warning("PyYAML not installed — using built-in reco defaults.")
        return {}
    if not _CONFIG_PATH.exists():
        log.warning("reco_config.yaml missing — using built-in defaults.")
        return {}
    try:
        return yaml.safe_load(_CONFIG_PATH.read_text()) or {}
    except Exception as exc:  # noqa: BLE001
        log.error("Failed to parse reco_config.yaml (%s) — using defaults.", exc)
        return {}


@lru_cache(maxsize=1)
def get_reco_config() -> RecoConfig:
    """Parse reco_config.yaml into a RecoConfig (cached for process lifetime)."""
    raw = _load_yaml()
    cand_raw = raw.get("candidates", {})
    coll = cand_raw.get("collaborative", {})
    cont = cand_raw.get("content", {})
    vec = cand_raw.get("vector", {})
    pop = cand_raw.get("popularity", {})

    candidates = CandidateConfig(
        collaborative_enabled=coll.get("enabled", True),
        collaborative_user_history_limit=coll.get("user_history_limit", 50),
        collaborative_neighbors_per_seed=coll.get("neighbors_per_seed", 20),
        content_enabled=cont.get("enabled", True),
        content_limit=cont.get("limit", 150),
        content_price_band_pct=cont.get("price_band_pct", 0.30),
        vector_enabled=vec.get("enabled", True),
        vector_limit=vec.get("limit", 100),
        popularity_enabled=pop.get("enabled", True),
        popularity_limit=pop.get("limit", 100),
    )
    reranker = raw.get("reranker", {})
    return RecoConfig(
        interaction_weights={**_DEFAULT_INTERACTION_WEIGHTS,
                             **raw.get("interaction_weights", {})},
        time_decay_lambda=raw.get("time_decay_lambda", 0.05),
        ranker_weights={**_DEFAULT_RANKER_WEIGHTS,
                        **raw.get("ranker", {}).get("feature_weights", {})},
        mmr_lambda=reranker.get("mmr_lambda", 0.7),
        max_per_brand=reranker.get("max_per_brand", 3),
        max_per_model=reranker.get("max_per_model", 2),
        top_k=raw.get("top_k", 20),
        candidate_pool_size=raw.get("candidate_pool_size", 300),
        candidates=candidates,
    )
