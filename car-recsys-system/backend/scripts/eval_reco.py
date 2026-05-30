"""Offline evaluation of the recommendation engine.

Leave-last-out protocol: for every user with enough history, hide their most
recent interaction, generate recommendations from the rest, and check whether
the hidden vehicle (or another listing of the same car model) is recovered.

Reports Hit-Rate@K, Precision@K, Recall@K, NDCG@K, catalog Coverage and
intra-list Diversity — the numbers to put in the thesis.

Usage:
    cd car-recsys-system/backend
    python scripts/eval_reco.py --k 20 --min-history 3
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text          # noqa: E402
from sqlalchemy.orm import sessionmaker              # noqa: E402

from app.core.config import settings                # noqa: E402
from app.services.reco import RecommendationEngine  # noqa: E402


def _dcg(hits: list[int]) -> float:
    return sum(h / math.log2(i + 2) for i, h in enumerate(hits))


def evaluate(k: int, min_history: int) -> dict[str, float]:
    engine = create_engine(settings.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()
    reco = RecommendationEngine(db)

    # Users with at least min_history interactions.
    users = db.execute(text("""
        SELECT user_id::text, count(*) AS n
        FROM gold.user_interactions
        GROUP BY user_id
        HAVING count(*) >= :min_history
    """), {"min_history": min_history}).fetchall()

    catalog_size = db.execute(
        text("SELECT count(*) FROM gold.vehicles")).scalar() or 1

    # car_model lookup for "soft" hits (same model counts as a hit).
    model_of: dict[str, str] = {
        r[0]: r[1] for r in db.execute(
            text("SELECT vehicle_id, car_model FROM gold.vehicles"))
    }

    n_users = 0
    hit_rate = precision = recall = ndcg = 0.0
    recommended_items: set[str] = set()
    diversity_sum = 0.0

    for user_id, _ in users:
        # The held-out (most recent) interaction.
        held = db.execute(text("""
            SELECT vehicle_id FROM gold.user_interactions
            WHERE user_id = :uid::uuid
            ORDER BY created_at DESC LIMIT 1
        """), {"uid": user_id}).fetchone()
        if not held:
            continue
        target = held[0]
        target_model = model_of.get(target)

        recs = reco.recommend_for_user(user_id, top_k=k)
        rec_ids = [r.vehicle_id for r in recs]
        if not rec_ids:
            continue
        n_users += 1
        recommended_items.update(rec_ids)

        hits = [
            1 if (vid == target
                  or (target_model and model_of.get(vid) == target_model))
            else 0
            for vid in rec_ids
        ]
        n_hits = sum(hits)
        hit_rate += 1.0 if n_hits else 0.0
        precision += n_hits / len(rec_ids)
        recall += 1.0 if n_hits else 0.0          # single held-out item
        ndcg += _dcg(hits) / (_dcg([1]) or 1.0)

        # Intra-list diversity: fraction of distinct car models in the list.
        models = [model_of.get(v) for v in rec_ids if model_of.get(v)]
        diversity_sum += (len(set(models)) / len(models)) if models else 0.0

    if n_users == 0:
        return {"users_evaluated": 0}

    return {
        "users_evaluated": n_users,
        f"hit_rate@{k}": round(hit_rate / n_users, 4),
        f"precision@{k}": round(precision / n_users, 4),
        f"recall@{k}": round(recall / n_users, 4),
        f"ndcg@{k}": round(ndcg / n_users, 4),
        "coverage": round(len(recommended_items) / catalog_size, 4),
        "diversity": round(diversity_sum / n_users, 4),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Offline reco evaluation")
    ap.add_argument("--k", type=int, default=20, help="top-K cutoff")
    ap.add_argument("--min-history", type=int, default=3,
                    help="minimum interactions for a user to be evaluated")
    args = ap.parse_args()

    metrics = evaluate(args.k, args.min_history)
    print("\n=== Recommendation engine — offline evaluation ===")
    if metrics.get("users_evaluated", 0) == 0:
        print("No users with enough interaction history — seed interactions first.")
        return 0
    for key, value in metrics.items():
        print(f"  {key:20s}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
