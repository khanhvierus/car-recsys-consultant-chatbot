"""Item-item collaborative-filtering similarity.

Builds a time-decayed, interaction-weighted user-item matrix from
gold.user_interactions, computes cosine item-item similarity, and writes the
top-N neighbors per vehicle into gold.item_similarity (TRUNCATE + INSERT).

The recommendation engine reads gold.item_similarity directly, so it never has
to fit a model in-request.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# Mirror of reco_config.yaml interaction weights — keep in sync.
_WEIGHTS = {
    "view": 1.0, "click": 2.0, "compare": 3.0,
    "save": 4.0, "favorite": 4.0, "contact": 8.0, "inquiry": 8.0,
}


def compute_item_similarity(
    warehouse_dsn: str,
    top_n: int = 50,
    decay_lambda: float = 0.05,
    lookback_days: int = 180,
) -> dict[str, int]:
    """Recompute gold.item_similarity. Returns {items, pairs} counts."""
    import numpy as np
    import psycopg2
    from psycopg2.extras import execute_values
    from scipy.sparse import csr_matrix
    from sklearn.metrics.pairwise import cosine_similarity

    conn = psycopg2.connect(warehouse_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id::text, vehicle_id, interaction_type, created_at
                FROM gold.user_interactions
                WHERE created_at >= now() - make_interval(days => %s)
                """,
                (lookback_days,),
            )
            rows = cur.fetchall()

        if not rows:
            log.warning("no interactions in lookback window — item_similarity left empty")
            with conn.cursor() as cur:
                cur.execute("TRUNCATE gold.item_similarity")
            conn.commit()
            return {"items": 0, "pairs": 0}

        # --- build the weighted user-item matrix ---
        users: dict[str, int] = {}
        items: list[str] = []
        item_idx: dict[str, int] = {}
        now = datetime.now(timezone.utc)
        cell: dict[tuple[int, int], float] = {}

        for user_id, vehicle_id, itype, created_at in rows:
            u = users.setdefault(user_id, len(users))
            if vehicle_id not in item_idx:
                item_idx[vehicle_id] = len(items)
                items.append(vehicle_id)
            i = item_idx[vehicle_id]
            ts = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
            days = max(0.0, (now - ts).total_seconds() / 86400.0)
            weight = _WEIGHTS.get(itype, 1.0) * math.exp(-decay_lambda * days)
            cell[(u, i)] = cell.get((u, i), 0.0) + weight

        n_users, n_items = len(users), len(items)
        if n_items < 2:
            log.warning("fewer than 2 interacted items — nothing to correlate")
            return {"items": n_items, "pairs": 0}

        r, c, d = zip(*[(u, i, w) for (u, i), w in cell.items()])
        ui = csr_matrix((d, (r, c)), shape=(n_users, n_items))

        # item-item cosine similarity (items as rows = transpose)
        sim = cosine_similarity(ui.T, dense_output=True)
        np.fill_diagonal(sim, 0.0)

        # --- top-N neighbors per item ---
        out_rows: list[tuple] = []
        k = min(top_n, n_items - 1)
        for i in range(n_items):
            order = np.argsort(sim[i])[::-1][:k]
            for rank, j in enumerate(order, start=1):
                score = float(sim[i, j])
                if score <= 0:
                    break
                out_rows.append((items[i], items[j], score, rank))

        # --- atomic refresh ---
        with conn.cursor() as cur:
            cur.execute("TRUNCATE gold.item_similarity")
            if out_rows:
                execute_values(
                    cur,
                    """INSERT INTO gold.item_similarity
                       (vehicle_id, neighbor_id, score, rank) VALUES %s""",
                    out_rows,
                    page_size=1000,
                )
        conn.commit()
        log.info("item_similarity: %d items, %d neighbor pairs", n_items, len(out_rows))
        return {"items": n_items, "pairs": len(out_rows)}
    finally:
        conn.close()
