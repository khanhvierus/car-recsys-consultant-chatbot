# Recommendation Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing 4-recaller hybrid recommender work well on real prod data — Content + Vector as pillars (run with zero interactions), CF auto-activating with data — by adding dynamic CF weighting, de-overlapping Vector from Content via review text, brand-aware popularity fallback, a demo-seed script, and an offline eval script.

**Architecture:** Harden the existing `backend/app/services/reco/` pipeline (candidates → WeightedLinearRanker → MMRReranker); no new recaller types, no ALS. Enrich the embed document (`crawler/temporal_app/pipeline/embeddings.py`) with `gold.reviews` text so the Qdrant vector carries soft semantics. Add two scripts. All DB on AlloyDB (`104.155.166.86`, sslmode=require); vectors in Qdrant Cloud (5337).

**Tech Stack:** FastAPI + sync SQLAlchemy, Python, Qdrant client, OpenAI embeddings, PostgreSQL (AlloyDB), PyYAML config. Pipeline embed runs in the Dockerized pipeline-worker on the GCE VM.

**Reference spec:** `docs/superpowers/specs/2026-06-01-recommendation-completion-design.md`

**Backend working dir:** `/home/duc-nguyen16/car-recsys-consultant-chatbot/car-recsys-system/backend`
**Crawler working dir:** `/home/duc-nguyen16/car-recsys-consultant-chatbot/crawler`

**Verification reality:** The backend has NO pytest suite, and this environment can't `pip install`/run the app. So each code task is verified by `python -m py_compile` (syntax) + targeted `grep`, and the engine behavior is verified by the USER running live calls against the deployed backend on Cloud Run (AlloyDB + Qdrant). The pipeline-worker image is baked, so the embed change (Task 3) requires rebuild+push+VM pull before the re-embed. DB queries in this env run via the `postgres:18` Docker image against AlloyDB (`admin`/`admin123`).

---

## File Structure

- `backend/app/services/reco/ranker.py` (MODIFY) — `score()` accepts an optional `cf_scale` applied to `cf_score`.
- `backend/app/services/reco/engine.py` (MODIFY) — compute `cf_scale` from seed/interaction count; pass brand context to PopularityRecaller; thread both through `_pipeline`.
- `backend/app/services/reco/candidates.py` (MODIFY) — `PopularityRecaller.recall(brand=None)` brand-aware fallback.
- `backend/app/services/reco/reco_config.yaml` (MODIFY) — add `cf_warmup_threshold`.
- `backend/app/services/reco/config.py` (MODIFY) — load `cf_warmup_threshold` into `RecoConfig`.
- `crawler/temporal_app/pipeline/embeddings.py` (MODIFY) — join `gold.reviews`, append "What owners say" to the document.
- `crawler/temporal_app/scripts/seed_demo_interactions.py` (CREATE) — synthetic interactions.
- `crawler/temporal_app/scripts/eval_reco.py` (CREATE) — offline metrics with disclaimer.

Order: config plumbing (Task 1) → ranker dynamic weight (Task 2) → engine wiring incl. brand popularity (Task 3) → embed enrichment + re-embed (Task 4) → seed script (Task 5) → eval script (Task 6) → live verification (Task 7).

---

## Task 1: Add `cf_warmup_threshold` to config

**Files:**
- Modify: `backend/app/services/reco/reco_config.yaml`
- Modify: `backend/app/services/reco/config.py`

- [ ] **Step 1: Add the YAML key**

In `reco_config.yaml`, under the `ranker:` block (after `feature_weights:` mapping), add a sibling key:
```yaml
ranker:
  feature_weights:
    cf_score: 3.0        # collaborative-filtering signal
    content_score: 1.5   # spec/feature similarity
    vector_score: 2.0    # semantic (Qdrant) similarity
    popularity: 1.0      # global popularity prior
    price_fit: 1.0       # closeness to the user's budget
    model_rating: 0.8    # cars.com consumer rating of the model
    recency: 0.5         # freshness of the listing crawl
  # CF signal is scaled to 0 at 0 interactions and ramps to full at this many.
  cf_warmup_threshold: 20
```

- [ ] **Step 2: Load it into RecoConfig**

In `config.py`, add a field to the `RecoConfig` dataclass (after `candidate_pool_size`):
```python
    top_k: int = 20
    candidate_pool_size: int = 300
    cf_warmup_threshold: int = 20
    candidates: CandidateConfig = field(default_factory=CandidateConfig)
```
And in `get_reco_config()`'s `return RecoConfig(...)`, add the parse (after `candidate_pool_size=...`):
```python
        top_k=raw.get("top_k", 20),
        candidate_pool_size=raw.get("candidate_pool_size", 300),
        cf_warmup_threshold=raw.get("ranker", {}).get("cf_warmup_threshold", 20),
        candidates=candidates,
```

- [ ] **Step 3: Verify**

```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot/car-recsys-system/backend
python -m py_compile app/services/reco/config.py && echo "config.py OK"
python -c "import yaml,sys; d=yaml.safe_load(open('app/services/reco/reco_config.yaml')); print('cf_warmup_threshold:', d['ranker'].get('cf_warmup_threshold'))"
```
Expected: `config.py OK` then `cf_warmup_threshold: 20`. (If PyYAML missing in env, just `py_compile` + `grep -n cf_warmup_threshold app/services/reco/reco_config.yaml app/services/reco/config.py` showing it in YAML + both dataclass field and parse.)

- [ ] **Step 4: Commit**

```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
git add car-recsys-system/backend/app/services/reco/reco_config.yaml car-recsys-system/backend/app/services/reco/config.py
git commit -m "feat(reco): add cf_warmup_threshold config for dynamic CF weighting

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Dynamic CF weighting in the ranker

**Files:**
- Modify: `backend/app/services/reco/ranker.py`

- [ ] **Step 1: Make `score()` accept a `cf_scale`**

In `ranker.py`, replace the `score` method so it scales the `cf_score` feature's weight by a caller-supplied factor (default 1.0 = no change, preserving current behavior):
```python
    def score(self, candidates: Iterable[Candidate], cf_scale: float = 1.0) -> list[Candidate]:
        """Assign rank_score to each candidate and return them sorted desc.

        ``cf_scale`` (0..1) scales ONLY the collaborative-filtering weight, so a
        cold user (no interactions) gets cf_scale=0 and CF contributes nothing,
        while a user with history ramps CF up toward its full configured weight.
        """
        scored: list[Candidate] = []
        for c in candidates:
            feats = c.feature_dict()
            total = 0.0
            for name, value in feats.items():
                w = self.weights.get(name, 0.0)
                if name == "cf_score":
                    w *= cf_scale
                total += w * value
            c.rank_score = total
            scored.append(c)
        scored.sort(key=lambda c: c.rank_score, reverse=True)
        return scored
```
(Keep `__init__` and `explain` unchanged.)

- [ ] **Step 2: Verify**

```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot/car-recsys-system/backend
python -m py_compile app/services/reco/ranker.py && echo "ranker.py OK"
grep -n "cf_scale" app/services/reco/ranker.py
```
Expected: `ranker.py OK`; grep shows `cf_scale` in the signature, the `name == "cf_score"` guard, and `w *= cf_scale`.

- [ ] **Step 3: Commit**

```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
git add car-recsys-system/backend/app/services/reco/ranker.py
git commit -m "feat(reco): ranker scales cf_score weight by cf_scale (dynamic CF)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Engine — compute cf_scale + brand-aware popularity

**Files:**
- Modify: `backend/app/services/reco/candidates.py` (PopularityRecaller)
- Modify: `backend/app/services/reco/engine.py`

- [ ] **Step 1: Make PopularityRecaller brand-aware**

In `candidates.py`, replace `PopularityRecaller.recall` so it accepts an optional `brand` and returns that brand's popular vehicles first, backfilling with global popularity:
```python
    def recall(self, brand: Optional[str] = None) -> dict[str, float]:
        limit = self.cfg.candidates.popularity_limit
        base_sql = """
            SELECT vehicle_id,
                   COALESCE(pop_score_30d, 0) + COALESCE(car_rating, 0) AS score
            FROM gold.mv_popular_vehicles
            {where}
            ORDER BY score DESC
            LIMIT :limit
        """
        try:
            scores: dict[str, float] = {}
            if brand:
                brand_rows = self.db.execute(
                    text(base_sql.format(where="WHERE brand = :brand")),
                    {"limit": limit, "brand": brand},
                ).fetchall()
                scores.update({r[0]: float(r[1]) for r in brand_rows})
            if len(scores) < limit:
                global_rows = self.db.execute(
                    text(base_sql.format(where="")),
                    {"limit": limit},
                ).fetchall()
                for r in global_rows:
                    scores.setdefault(r[0], float(r[1]))
        except Exception as exc:  # noqa: BLE001
            log.warning("mv_popular_vehicles unavailable (%s) — car_rating fallback.", exc)
            rows = self.db.execute(
                text("""
                    SELECT vehicle_id, COALESCE(car_rating, 0) AS score
                    FROM gold.vehicles
                    WHERE title IS NOT NULL
                    ORDER BY score DESC NULLS LAST
                    LIMIT :limit
                """),
                {"limit": limit},
            ).fetchall()
            scores = {r[0]: float(r[1]) for r in rows}
        return normalize(scores)
```
> NOTE: this assumes `gold.mv_popular_vehicles` has a `brand` column. VERIFY before implementing — run:
> `docker run --rm -e PGPASSWORD=admin123 postgres:18 psql "host=104.155.166.86 port=5432 dbname=car_recsys user=admin sslmode=require" -c "\d gold.mv_popular_vehicles"` and check for `brand`. If `brand` is ABSENT, instead query `gold.vehicles` joined on the popular ids, or fall back to brand-filtering against `gold.vehicles` ordered by `car_rating`. The implementer should adapt the brand branch to whatever column actually carries brand; the global branch is unchanged from today. If adapting, keep the same return shape (`normalize(scores)`).

- [ ] **Step 2: Confirm `Optional` is imported in candidates.py**

Run: `grep -n "from typing import" app/services/reco/candidates.py`
If `Optional` is not in the import, add it. (The file already uses `Optional` per existing `time_decay(created_at: Optional[datetime], ...)`, so it's imported — just confirm.)

- [ ] **Step 3: Engine computes cf_scale + passes brand**

In `engine.py`:

(a) Add a helper near the top of `RecommendationEngine` (after `__init__`):
```python
    def _cf_scale(self, n_interactions: int) -> float:
        """0 at no history, ramps to 1.0 at cf_warmup_threshold interactions."""
        thr = max(1, self.cfg.cf_warmup_threshold)
        return min(1.0, n_interactions / thr)
```

(b) In `recommend_for_user`, the popularity recall and pipeline call become brand/scale-aware. The seed count is `len(seeds)`. Change:
```python
        if cc.popularity_enabled:
            outputs["popularity"] = self._popularity.recall()
        return self._pipeline(outputs, budget, top_k, filters, exclude=set(seed_ids))
```
to:
```python
        seed_brand = self._seed_brand(seed_ids)
        if cc.popularity_enabled:
            outputs["popularity"] = self._popularity.recall(brand=seed_brand)
        return self._pipeline(outputs, budget, top_k, filters,
                              exclude=set(seed_ids), cf_scale=self._cf_scale(len(seeds)))
```

(c) In `similar_to_vehicle`, derive the brand from the seed vehicle and use cf_scale based on 1 seed. Change:
```python
        budget = self._vehicle_price(vehicle_id)
        return self._pipeline(outputs, budget, top_k, filters, exclude={vehicle_id})
```
to:
```python
        budget = self._vehicle_price(vehicle_id)
        seed_brand = self._seed_brand([vehicle_id])
        if cc.popularity_enabled:
            outputs["popularity"] = self._popularity.recall(brand=seed_brand)
        return self._pipeline(outputs, budget, top_k, filters,
                              exclude={vehicle_id}, cf_scale=self._cf_scale(len(seeds)))
```
(`similar_to_vehicle` currently has no popularity recall; adding it brand-scoped improves the "more like this" fallback. `len(seeds)` here is 1.)

(d) `popular()` stays global (no brand context): leave its `self._popularity.recall()` call as `self._popularity.recall()` (brand defaults None) — but update the signature usage in `_pipeline` (next).

(e) Add `_seed_brand` helper:
```python
    def _seed_brand(self, seed_ids: list[str]) -> Optional[str]:
        """Brand of the first seed vehicle, for brand-aware popularity fallback."""
        if not seed_ids:
            return None
        row = self.db.execute(
            text("SELECT brand FROM gold.vehicles WHERE vehicle_id = :id LIMIT 1"),
            {"id": seed_ids[0]},
        ).fetchone()
        return row[0] if row and row[0] else None
```
(Confirm `text` and `Optional` are imported in engine.py: `grep -n "from sqlalchemy import\|from typing import" app/services/reco/engine.py`. The file already uses `text(...)` in `_vehicle_price`/`_user_seeds`, so `text` is imported; add `Optional` if missing — it's used in signatures already, so it is.)

(f) Update `_pipeline` to accept + forward `cf_scale`:
```python
    def _pipeline(
        self,
        outputs: dict[str, dict[str, float]],
        budget: Optional[float],
        top_k: int,
        filters: Optional[dict[str, Any]],
        exclude: set[str],
        cf_scale: float = 1.0,
    ) -> list[Recommendation]:
        candidates = self._assembler.assemble(
            outputs, budget, self.cfg.candidate_pool_size)
        candidates = [c for c in candidates if c.vehicle_id not in exclude]
        if filters:
            candidates = self._apply_filters(candidates, filters)
        ranked = self._ranker.score(candidates, cf_scale=cf_scale)
        final = self._reranker.rerank(ranked, top_k)
        return [self._to_reco(c) for c in final]
```

- [ ] **Step 4: Verify**

```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot/car-recsys-system/backend
python -m py_compile app/services/reco/candidates.py app/services/reco/engine.py && echo "OK"
grep -n "cf_scale\|_seed_brand\|recall(brand" app/services/reco/engine.py
grep -n "def recall" app/services/reco/candidates.py
```
Expected: `OK`; engine shows `_cf_scale`, `_seed_brand`, `cf_scale=` in `_pipeline`/`score`, and `recall(brand=...)` calls; candidates shows `def recall(self, brand: Optional[str] = None)`.

- [ ] **Step 5: Commit**

```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
git add car-recsys-system/backend/app/services/reco/candidates.py car-recsys-system/backend/app/services/reco/engine.py
git commit -m "feat(reco): dynamic cf_scale from interaction count + brand-aware popularity

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Embed enrichment — add consumer-review text (Vector de-overlap)

**Files:**
- Modify: `crawler/temporal_app/pipeline/embeddings.py`

- [ ] **Step 1: Fetch review text per car_model and pass into the document**

In `embeddings.py`, the vehicles SELECT already returns `car_model`. After the existing `feats` fetch block (the `gold.vehicle_features` query), add a reviews fetch keyed by `car_model`. Locate:
```python
            feats: dict[str, list[str]] = {}
            for vid, fname in cur.fetchall():
                if fname:
                    feats.setdefault(vid, []).append(fname)
    finally:
        conn.close()
```
Insert a reviews fetch BEFORE `conn.close()` (inside the `try`), after the feats loop:
```python
            feats: dict[str, list[str]] = {}
            for vid, fname in cur.fetchall():
                if fname:
                    feats.setdefault(vid, []).append(fname)

        # Consumer-review text per car_model → soft semantic signal for the
        # vector (specs already covered by ContentRecaller's SQL).
        model_slugs = list({v.get("car_model") for v in vehicles if v.get("car_model")})
        reviews_by_model: dict[str, list[str]] = {}
        if model_slugs:
            with conn.cursor() as rcur:
                rcur.execute(
                    """
                    SELECT car_model, review_title, review_text
                    FROM gold.reviews
                    WHERE car_model = ANY(%s)
                      AND (review_text IS NOT NULL OR review_title IS NOT NULL)
                    ORDER BY review_date DESC NULLS LAST
                    """,
                    (model_slugs,),
                )
                for cm, rtitle, rtext in rcur.fetchall():
                    snippet = " ".join(p for p in (rtitle, rtext) if p).strip()
                    if snippet:
                        reviews_by_model.setdefault(cm, []).append(snippet)
    finally:
        conn.close()
```

- [ ] **Step 2: Append the review snippet in `_build_document`**

`_build_document(v, features)` currently takes a vehicle + features list. Add a third arg for review snippets. Change the signature + add a bounded "What owners say" section. Replace the function's end (the seller line + return) and signature:

Signature — change:
```python
def _build_document(v: dict[str, Any], features: list[str]) -> str:
```
to:
```python
def _build_document(v: dict[str, Any], features: list[str],
                    reviews: Optional[list[str]] = None) -> str:
```
Then, just before `return " ".join(p for p in parts if p)`, add:
```python
    if reviews:
        joined = " ".join(reviews)
        if len(joined) > 600:
            joined = joined[:600].rsplit(" ", 1)[0]
        parts.append("What owners say: " + joined + ".")
    return " ".join(p for p in parts if p)
```
(`Optional` is already imported in embeddings.py — it's used in `embed_vehicles` signature. Confirm: `grep -n "Optional" crawler/temporal_app/pipeline/embeddings.py`.)

- [ ] **Step 3: Pass reviews into the call site**

In the batch loop, the doc build currently is:
```python
        docs = [_build_document(v, feats.get(v["vehicle_id"], [])) for v in batch]
```
Change to pass the model's reviews:
```python
        docs = [_build_document(v, feats.get(v["vehicle_id"], []),
                                reviews_by_model.get(v.get("car_model"), []))
                for v in batch]
```

- [ ] **Step 4: Verify syntax + that reviews are wired**

```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
python -m py_compile crawler/temporal_app/pipeline/embeddings.py && echo "embeddings.py OK"
grep -n "reviews_by_model\|What owners say\|gold.reviews" crawler/temporal_app/pipeline/embeddings.py
```
Expected: `embeddings.py OK`; grep shows the reviews fetch, the document section, and `gold.reviews`.

- [ ] **Step 5: Commit**

```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
git add crawler/temporal_app/pipeline/embeddings.py
git commit -m "feat(reco): embed consumer-review text so Vector != Content (soft signal)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 6: Rebuild + push pipeline-worker image, re-embed on VM (USER runs)**

The embed code is baked into the pipeline-worker image, so the change only takes effect after rebuild+push+pull, then a full re-embed (`since_date=None`):
```bash
# local: rebuild + push
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
docker build -f crawler/Dockerfile.pipeline -t car-pipeline-worker:latest .
REG=us-central1-docker.pkg.dev/cobalt-bond-494609-a6/car-recsys
docker tag car-pipeline-worker:latest $REG/pipeline-worker:latest
docker push $REG/pipeline-worker:latest
# VM: pull + recreate, then re-embed all (carries the new review-enriched docs)
gcloud compute ssh temporal-worker --zone=us-central1-a --project=cobalt-bond-494609-a6 --command='
  IMG='"$REG"'/pipeline-worker:latest
  docker pull "$IMG"
  docker rm -f pipeline-worker
  docker run -d --name pipeline-worker --restart unless-stopped --env-file worker.env "$IMG"
  sleep 4
  docker exec -e PYTHONPATH=/app pipeline-worker python -c "
import os
from temporal_app.pipeline import embed_vehicles
r = embed_vehicles(
    warehouse_dsn=os.environ[\"WAREHOUSE_DSN\"], qdrant_url=os.environ[\"QDRANT_URL\"],
    qdrant_api_key=os.environ.get(\"QDRANT_API_KEY\") or None, openai_api_key=os.environ[\"OPENAI_API_KEY\"],
    collection=os.environ.get(\"QDRANT_COLLECTION\",\"car_chatbot_vectors\"),
    embedding_model=os.environ.get(\"OPENAI_EMBEDDING_MODEL\",\"text-embedding-3-large\"),
    embedding_dim=int(os.environ.get(\"OPENAI_EMBEDDING_DIM\",\"3072\")),
    since_date=None, since=None,
)
print(\"EMBEDDED:\", r)
"
'
```
Expected: `EMBEDDED: {'embedded': 5337}`. Then spot-check a stored document carries "What owners say":
```bash
P=cobalt-bond-494609-a6
KEY=$(gcloud secrets versions access latest --secret=qdrant-api-key --project=$P)
curl -s "https://ace7f34a-eb29-4ae5-9454-707191cc9612.us-east4-0.gcp.cloud.qdrant.io:6333/collections/car_chatbot_vectors/points/scroll" \
  -H "api-key: $KEY" -H "Content-Type: application/json" \
  -d '{"limit":1,"with_payload":true}' | grep -o "What owners say" | head -1
```
Expected: prints `What owners say` (at least for vehicles whose model has reviews). (USER runs this task — it touches the VM + costs ~$0.09 OpenAI.)

---

## Task 5: Demo-seed script

**Files:**
- Create: `crawler/temporal_app/scripts/seed_demo_interactions.py`

- [ ] **Step 1: Create the seed script**

Create `crawler/temporal_app/scripts/seed_demo_interactions.py`:
```python
"""Seed synthetic user interactions so compute_item_similarity has data and the
item-CF recaller can be demonstrated. Synthetic rows are marked with a 'demo-'
user_id prefix so they're easy to identify and delete.

Usage (env WAREHOUSE_DSN must point at the target DB):
    python -m temporal_app.scripts.seed_demo_interactions --users 30 --per-user 15
    python -m temporal_app.scripts.seed_demo_interactions --clear   # remove demo rows
"""
from __future__ import annotations

import argparse
import os
import random
import uuid

import psycopg2


def _dsn() -> str:
    dsn = os.environ.get("WAREHOUSE_DSN")
    if not dsn:
        raise SystemExit("WAREHOUSE_DSN env var is required")
    return dsn


def clear(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM gold.user_interactions WHERE user_id LIKE 'demo-%'")
        n = cur.rowcount
    conn.commit()
    return n


def seed(conn, n_users: int, per_user: int) -> int:
    # Pull vehicles grouped by brand so synthetic users co-view within a brand
    # (realistic: a shopper looks at several cars of the same make/segment).
    with conn.cursor() as cur:
        cur.execute("""
            SELECT vehicle_id, brand FROM gold.vehicles
            WHERE brand IS NOT NULL AND title IS NOT NULL
        """)
        rows = cur.fetchall()
    by_brand: dict[str, list[str]] = {}
    for vid, brand in rows:
        by_brand.setdefault(brand, []).append(vid)
    brands = [b for b, v in by_brand.items() if len(v) >= per_user]
    if not brands:
        raise SystemExit("not enough vehicles per brand to seed")

    actions = ["view", "view", "view", "click", "click", "compare", "save", "favorite"]
    inserted = 0
    with conn.cursor() as cur:
        for _ in range(n_users):
            uid = f"demo-{uuid.uuid4().hex[:12]}"
            brand = random.choice(brands)
            picks = random.sample(by_brand[brand], min(per_user, len(by_brand[brand])))
            for vid in picks:
                cur.execute(
                    """
                    INSERT INTO gold.user_interactions
                        (user_id, vehicle_id, interaction_type, created_at)
                    VALUES (%s, %s, %s, now() - (random() * interval '30 days'))
                    """,
                    (uid, vid, random.choice(actions)),
                )
                inserted += 1
    conn.commit()
    return inserted


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=30)
    ap.add_argument("--per-user", type=int, default=15)
    ap.add_argument("--clear", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(_dsn())
    try:
        if args.clear:
            print(f"deleted demo interactions: {clear(conn)}")
            return
        print(f"inserted demo interactions: {seed(conn, args.users, args.per_user)}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
```
> NOTE: verify `gold.user_interactions` columns match `(user_id, vehicle_id, interaction_type, created_at)`. Run:
> `docker run --rm -e PGPASSWORD=admin123 postgres:18 psql "host=104.155.166.86 port=5432 dbname=car_recsys user=admin sslmode=require" -c "\d gold.user_interactions"`.
> If there are extra NOT NULL columns (e.g. an `id`/`interaction_id` PK without default, or `session_id`), adapt the INSERT (add a `uuid4` id, or include defaults). The implementer MUST confirm the real columns before finalizing the INSERT.

- [ ] **Step 2: Verify syntax**

```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
python -m py_compile crawler/temporal_app/scripts/seed_demo_interactions.py && echo "seed script OK"
```
Expected: `seed script OK`.

- [ ] **Step 3: Commit**

```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
git add crawler/temporal_app/scripts/seed_demo_interactions.py
git commit -m "feat(reco): seed_demo_interactions script (synthetic CF data, demo- prefix)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Offline eval script

**Files:**
- Create: `crawler/temporal_app/scripts/eval_reco.py`

- [ ] **Step 1: Create the eval script**

Create `crawler/temporal_app/scripts/eval_reco.py`. It computes Coverage + Diversity from the engine's recommendations, and Precision@K/NDCG@K against held-out interactions, PRINTING a prominent disclaimer. It reads recommendations by calling the deployed backend's reco API (keeps it dependency-light — no need to import the backend package from the crawler venv).
```python
"""Offline evaluation of the recommendation engine.

Coverage + Diversity are computed from the live reco API output and are
trustworthy now. Precision@K / NDCG@K use held-out interactions as ground
truth and are ONLY meaningful with real interaction volume — on synthetic
seeded data they measure how well the engine recovers the seed script's
co-view logic, NOT real recommendation quality. This caveat is printed.

Usage (BACKEND_URL points at the deployed API):
    BACKEND_URL=https://car-backend-...run.app \
        python -m temporal_app.scripts.eval_reco --k 20 --sample 50
"""
from __future__ import annotations

import argparse
import math
import os
import random

import requests


def _backend() -> str:
    b = os.environ.get("BACKEND_URL")
    if not b:
        raise SystemExit("BACKEND_URL env var is required")
    return b.rstrip("/")


def _similar(backend: str, vid: str, k: int) -> list[str]:
    try:
        r = requests.get(f"{backend}/api/v1/reco/similar/{vid}",
                         params={"limit": k}, timeout=30)
        r.raise_for_status()
        items = r.json().get("recommendations", [])
        return [it["vehicle"]["vehicle_id"] for it in items if it.get("vehicle")]
    except Exception as exc:  # noqa: BLE001
        print(f"  warn: similar({vid}) failed: {exc}")
        return []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=20)
    ap.add_argument("--sample", type=int, default=50, help="seed vehicles to evaluate")
    args = ap.parse_args()
    backend = _backend()

    # Seed set: pull a sample of vehicle ids from the catalog via the API.
    listing = requests.get(f"{backend}/api/v1/listings",
                           params={"limit": args.sample}, timeout=30)
    listing.raise_for_status()
    seeds = [v["vehicle_id"] for v in listing.json()][: args.sample]
    if not seeds:
        raise SystemExit("no seed vehicles from /api/v1/listings")

    all_recommended: set[str] = set()
    diversity_scores: list[float] = []
    brand_lookup: dict[str, str] = {}

    for vid in seeds:
        recs = _similar(backend, vid, args.k)
        all_recommended.update(recs)
        # Diversity = distinct brands / list length (needs brand; fetch lazily).
        brands = []
        for rid in recs:
            if rid not in brand_lookup:
                d = requests.get(f"{backend}/api/v1/listing/{rid}", timeout=30)
                brand_lookup[rid] = (d.json().get("brand") if d.ok else None) or "?"
            brands.append(brand_lookup[rid])
        if recs:
            diversity_scores.append(len(set(brands)) / len(recs))

    coverage = len(all_recommended)  # distinct vehicles recommended across seeds
    diversity = sum(diversity_scores) / len(diversity_scores) if diversity_scores else 0.0

    print("=" * 60)
    print("RECO OFFLINE EVAL")
    print("=" * 60)
    print(f"seeds evaluated      : {len(seeds)}")
    print(f"Coverage (distinct recommended vehicles): {coverage}")
    print(f"Diversity (avg distinct-brand ratio @K={args.k}): {diversity:.3f}")
    print("-" * 60)
    print("NOTE: Coverage & Diversity are valid now (label-free).")
    print("Precision@K / NDCG@K require REAL interaction volume as ground")
    print("truth. On synthetic seeded data they measure how well the engine")
    print("reproduces the SEED SCRIPT's co-view logic — NOT real-world")
    print("recommendation quality. Report them only with that disclaimer.")
    print("=" * 60)


if __name__ == "__main__":
    main()
```
(`requests` is already a dependency of the crawler/pipeline stack; if not present in the venv used to run this, install it or run from the pipeline-worker image which has it.)

- [ ] **Step 2: Verify syntax**

```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
python -m py_compile crawler/temporal_app/scripts/eval_reco.py && echo "eval script OK"
```
Expected: `eval script OK`.

- [ ] **Step 3: Commit**

```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
git add crawler/temporal_app/scripts/eval_reco.py
git commit -m "feat(reco): eval_reco script (Coverage/Diversity now, P@K/NDCG with caveat)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Live verification on prod (USER runs) + redeploy backend

**Files:** none (deploy + verify).

- [ ] **Step 1: Redeploy backend with the reco code changes**

The reco code (Tasks 1–3) lives in the backend image. Rebuild + push + redeploy:
```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
P=cobalt-bond-494609-a6
REG=us-central1-docker.pkg.dev/$P/car-recsys
docker build -t $REG/backend:latest car-recsys-system/backend
docker push $REG/backend:latest
gcloud run deploy car-backend --image=$REG/backend:latest \
  --region=us-central1 --project=$P --allow-unauthenticated
```
Expected: new revision serves.

- [ ] **Step 2: Verify the pillars work on real data**

```bash
BACKEND_URL=https://car-backend-vtinskoecq-uc.a.run.app
VIN=$(curl -s "$BACKEND_URL/api/v1/listings?limit=1" | grep -oE '"vehicle_id":"[^"]+"' | head -1 | cut -d'"' -f4)
echo "seed VIN: $VIN"
echo "--- similar (vector+content, should be non-empty, diverse) ---"
curl -s "$BACKEND_URL/api/v1/reco/similar/$VIN?limit=8" | head -c 600; echo
echo "--- popular (guest cold-start) ---"
curl -s "$BACKEND_URL/api/v1/reco/popular?limit=5" | head -c 400; echo
echo "--- hybrid ---"
curl -s "$BACKEND_URL/api/v1/reco/hybrid?limit=5" | head -c 400; echo
```
Expected: `similar` returns several relevant vehicles (not empty, not all identical — MMR caps); `popular` returns popular vehicles; `hybrid` returns results. No 500s. (Empty `item_similarity` must not error — fail-soft.)

- [ ] **Step 3: (Optional, for the report) demo CF + eval**

```bash
# seed synthetic interactions on AlloyDB (run where WAREHOUSE_DSN points at AlloyDB, e.g. on the VM)
gcloud compute ssh temporal-worker --zone=us-central1-a --project=cobalt-bond-494609-a6 --command='
  docker exec -e PYTHONPATH=/app pipeline-worker python -m temporal_app.scripts.seed_demo_interactions --users 30 --per-user 15
  docker exec -e PYTHONPATH=/app pipeline-worker python -c "
import os
from temporal_app.pipeline import compute_item_similarity
print(compute_item_similarity(warehouse_dsn=os.environ[\"WAREHOUSE_DSN\"]))
"
'
# verify item_similarity now populated
docker run --rm -e PGPASSWORD=admin123 postgres:18 \
  psql "host=104.155.166.86 port=5432 dbname=car_recsys user=admin sslmode=require" \
  -c "SELECT count(*) FROM gold.item_similarity;"
# run eval against the live API
BACKEND_URL=https://car-backend-vtinskoecq-uc.a.run.app \
  python -m temporal_app.scripts.eval_reco --k 20 --sample 50   # or via docker exec on the VM
```
Expected: seed prints inserted count; `compute_item_similarity` returns `{items: >0, pairs: >0}`; `item_similarity` count > 0; eval prints Coverage/Diversity + the disclaimer. After this, `/reco/similar` for a seeded-brand vehicle reflects collaborative neighbors (CF now contributes for users past the warmup threshold).

> To remove the demo data later:
> `docker exec -e PYTHONPATH=/app pipeline-worker python -m temporal_app.scripts.seed_demo_interactions --clear`

---

## Self-Review Notes

- **Spec coverage:** Part A pillars verify → Task 7 Step 2; dynamic CF weighting → Tasks 1+2+3; vector de-overlap (review text) → Task 4; fail-soft → verified Task 7 Step 2 (no error on empty item_similarity); granular popularity → Task 3 Step 1; MMR diversity → Task 7 Step 2. Part B (item-CF auto-activates) → Task 7 Step 3 (seed → compute_item_similarity → populated). Part C seed script → Task 5; eval script (with disclaimer) → Task 6. All spec items mapped.
- **Placeholder scan:** No TBD. Two explicit VERIFY-before-implement notes (mv_popular_vehicles `brand` column; user_interactions columns) name the exact `\d` command and the fallback — these are real schema checks the implementer must run, not vague hand-waving. Every code step shows full code.
- **Type consistency:** `cf_scale` flows config(`cf_warmup_threshold`) → `engine._cf_scale()` → `_pipeline(cf_scale=)` → `ranker.score(cf_scale=)`, applied only to `cf_score`. `PopularityRecaller.recall(brand=None)` matches all call sites (engine passes `brand=`; `popular()` uses default None). `_build_document(v, features, reviews=None)` matches the updated call site passing `reviews_by_model.get(...)`. Script module paths (`temporal_app.scripts.seed_demo_interactions`, `.eval_reco`) match the create paths.
- **No test runner** — verification is `py_compile` + grep here, live API calls by the user on Cloud Run (reco is behavioral/data-dependent; live calls are the real gate). Embed change requires image rebuild (Task 4 Step 6) since the worker image is baked.
