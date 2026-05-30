# Cloud Run Deploy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Host the Vite+React frontend and FastAPI backend on GCP Cloud Run (2 services, `*.run.app` URLs) so external users can access the app over public HTTPS, with the backend reaching Cloud SQL via the Cloud SQL Connector and Qdrant Cloud via api_key.

**Architecture:** Two Cloud Run services in `us-central1` — `car-backend` (FastAPI on `$PORT`, Cloud SQL unix socket, Qdrant Cloud) and `car-frontend` (nginx serving the Vite build, built with `VITE_API_URL=<backend URL>`). Deploy backend first (CORS open during bring-up), then frontend, then tighten CORS. Secrets via Secret Manager.

**Tech Stack:** Cloud Run, Artifact Registry, Cloud SQL Connector, Secret Manager, Docker (multi-stage nginx for frontend), FastAPI, Vite, gcloud CLI.

**Reference spec:** `docs/superpowers/specs/2026-05-31-cloud-run-deploy-design.md`

**Constants used throughout:**
- Project: `cobalt-bond-494609-a6`
- Region: `us-central1`
- Cloud SQL instance connection name: `cobalt-bond-494609-a6:us-central1:free-trial-first-project`
- Artifact Registry: `us-central1-docker.pkg.dev/cobalt-bond-494609-a6/car-recsys`
- Qdrant Cloud URL: `https://ace7f34a-eb29-4ae5-9454-707191cc9612.us-east4-0.gcp.cloud.qdrant.io:6333`

---

## File Structure

- `car-recsys-system/backend/app/core/config.py` (modify) — add `QDRANT_API_KEY`; drop `"*"` from prod CORS list.
- `car-recsys-system/backend/app/api/v1/recommendations.py` (modify) — pass api_key to QdrantClient.
- `car-recsys-system/backend/app/services/chatbot/core.py` (modify) — pass api_key to QdrantClient.
- `car-recsys-system/backend/Dockerfile` (modify) — production CMD listening on `$PORT`, no `--reload`.
- `car-recsys-system/frontend/Dockerfile` (rewrite) — multi-stage build + nginx.
- `car-recsys-system/frontend/nginx.conf` (modify) — `listen 8080`.
- No new test files: backend has no pytest suite; verification is via live `curl`/browser per the spec. Each code task includes an import/parse check.

---

## Task 1: Backend — Qdrant api_key support

**Files:**
- Modify: `car-recsys-system/backend/app/core/config.py`
- Modify: `car-recsys-system/backend/app/api/v1/recommendations.py`
- Modify: `car-recsys-system/backend/app/services/chatbot/core.py`

- [ ] **Step 1: Add QDRANT_API_KEY to config**

In `car-recsys-system/backend/app/core/config.py`, find the Vector Database block:
```python
    # Vector Database
    QDRANT_URL: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION", "car_chatbot_vectors")
```
Add a `QDRANT_API_KEY` line after it:
```python
    # Vector Database
    QDRANT_URL: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION", "car_chatbot_vectors")
    QDRANT_API_KEY: str = os.getenv("QDRANT_API_KEY", "")
```

- [ ] **Step 2: Pass api_key in recommendations.py**

In `car-recsys-system/backend/app/api/v1/recommendations.py`, change the QdrantClient construction (inside `_get_qdrant`):
```python
            from qdrant_client import QdrantClient
            _qdrant_client = QdrantClient(url=settings.QDRANT_URL)
```
to:
```python
            from qdrant_client import QdrantClient
            _qdrant_client = QdrantClient(
                url=settings.QDRANT_URL,
                api_key=settings.QDRANT_API_KEY or None,
            )
```

- [ ] **Step 3: Pass api_key in chatbot/core.py**

In `car-recsys-system/backend/app/services/chatbot/core.py`, change:
```python
    qdrant = QdrantClient(url=settings.QDRANT_URL)
```
to:
```python
    qdrant = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)
```

- [ ] **Step 4: Verify backend imports cleanly**

Run (from repo root):
```bash
cd car-recsys-system/backend && python -c "from app.core.config import settings; print('QDRANT_API_KEY' in dir(settings) or hasattr(settings,'QDRANT_API_KEY')); print(settings.QDRANT_API_KEY == '')"
```
Expected: `True` then `True` (key present, empty default). If `pydantic`/deps not
installed locally, instead grep-verify: `grep -n QDRANT_API_KEY app/core/config.py app/api/v1/recommendations.py app/services/chatbot/core.py` shows the key in config and both `api_key=settings.QDRANT_API_KEY` call sites.

- [ ] **Step 5: Commit**

```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
git add car-recsys-system/backend/app/core/config.py car-recsys-system/backend/app/api/v1/recommendations.py car-recsys-system/backend/app/services/chatbot/core.py
git commit -m "feat(backend): Qdrant api_key for Qdrant Cloud"
```

---

## Task 2: Backend — production Dockerfile + CORS tightening

**Files:**
- Modify: `car-recsys-system/backend/Dockerfile`
- Modify: `car-recsys-system/backend/app/core/config.py`

- [ ] **Step 1: Production CMD listening on $PORT**

In `car-recsys-system/backend/Dockerfile`, replace the final CMD line:
```dockerfile
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```
with:
```dockerfile
# Cloud Run injects $PORT (default 8080). No --reload in production.
ENV PORT=8080
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
```

- [ ] **Step 2: Remove the wildcard from the prod CORS list**

In `car-recsys-system/backend/app/core/config.py`, the `BACKEND_CORS_ORIGINS`
list contains `"*"`, which would defeat production CORS restriction. Remove that
one entry:
```python
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
        "http://frontend:3000",
        "*",  # Allow all origins in development
    ]
```
becomes (drop the `"*"` line):
```python
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
        "http://frontend:3000",
    ]
```
(`main.py` still uses `["*"]` when `ENVIRONMENT=="development"`, so local dev is
unaffected. In production, CORS is restricted to `BACKEND_CORS_ORIGINS`, which we
set to the real frontend URL at deploy time in Task 6.)

- [ ] **Step 3: Build backend image locally to catch errors**

```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot/car-recsys-system/backend
docker build -t car-backend:latest . 2>&1 | tail -3
```
Expected: `naming to docker.io/library/car-backend:latest` (build succeeds).

- [ ] **Step 4: Smoke-run the image (imports + starts, no DB needed for /docs)**

```bash
docker run --rm -d --name be-test -p 8080:8080 -e PORT=8080 car-backend:latest
sleep 5
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/docs
docker rm -f be-test
```
Expected: `200` (Swagger served — proves uvicorn boots on $PORT). If it's not 200,
`docker logs be-test` before removing to see the import/startup error.

- [ ] **Step 5: Commit**

```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
git add car-recsys-system/backend/Dockerfile car-recsys-system/backend/app/core/config.py
git commit -m "feat(backend): production Dockerfile (\$PORT) + restrict prod CORS"
```

---

## Task 3: Frontend — multi-stage nginx Dockerfile

**Files:**
- Modify: `car-recsys-system/frontend/Dockerfile`
- Modify: `car-recsys-system/frontend/nginx.conf`

- [ ] **Step 1: nginx listens on 8080 (Cloud Run port)**

In `car-recsys-system/frontend/nginx.conf`, change:
```
    listen 3000;
```
to:
```
    listen 8080;
```

- [ ] **Step 2: Rewrite frontend Dockerfile to build + nginx**

Replace the ENTIRE `car-recsys-system/frontend/Dockerfile` with:
```dockerfile
# Build stage — produce the static Vite bundle.
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json bun.lockb* package-lock.json* ./
RUN npm ci 2>/dev/null || npm install
COPY . .
# VITE_API_URL is inlined at build time (Vite). Pass it as a build arg.
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# Serve stage — nginx serves the static bundle on $PORT (8080).
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
```

- [ ] **Step 3: Build frontend image with a test API URL**

```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot/car-recsys-system/frontend
docker build --build-arg VITE_API_URL=https://example.com -t car-frontend:latest . 2>&1 | tail -4
```
Expected: `naming to docker.io/library/car-frontend:latest`. (If `npm run build`
fails on a TypeScript error, that's a real frontend bug — report it; do NOT paper
over with `|| true`.)

- [ ] **Step 4: Smoke-run frontend image (nginx serves index on 8080)**

```bash
docker run --rm -d --name fe-test -p 8081:8080 car-frontend:latest
sleep 3
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8081/
docker rm -f fe-test
```
Expected: `200` (nginx serves index.html). Also confirm SPA fallback:
`curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8081/some/spa/route` → `200`.

- [ ] **Step 5: Commit**

```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
git add car-recsys-system/frontend/Dockerfile car-recsys-system/frontend/nginx.conf
git commit -m "feat(frontend): multi-stage nginx Dockerfile for Cloud Run"
```

---

## Task 4: Secrets in Secret Manager

**Files:** none (gcloud only).

- [ ] **Step 1: Enable Secret Manager API**

```bash
gcloud services enable secretmanager.googleapis.com --project=cobalt-bond-494609-a6
```

- [ ] **Step 2: Create the three secrets**

Replace each `<...>` with the real value (do NOT echo secrets into shell history if
avoidable — use a file or `read -s`). Example with printf:
```bash
P=--project=cobalt-bond-494609-a6
printf '%s' '<OPENAI_KEY>'  | gcloud secrets create openai-api-key  --data-file=- $P
printf '%s' '<QDRANT_KEY>'  | gcloud secrets create qdrant-api-key  --data-file=- $P
printf '%s' '<DB_PASSWORD>' | gcloud secrets create db-password     --data-file=- $P
```
(`<DB_PASSWORD>` is the Cloud SQL `admin` password, currently `admin123`.)

- [ ] **Step 3: Grant the Cloud Run service account access**

The default compute service account runs Cloud Run unless overridden. Grant it
secret access:
```bash
P=cobalt-bond-494609-a6
SA="$(gcloud projects describe $P --format='value(projectNumber)')-compute@developer.gserviceaccount.com"
for s in openai-api-key qdrant-api-key db-password; do
  gcloud secrets add-iam-policy-binding $s \
    --member="serviceAccount:$SA" \
    --role="roles/secretmanager.secretAccessor" --project=$P
done
```

- [ ] **Step 4: Verify secrets exist**

```bash
gcloud secrets list --project=cobalt-bond-494609-a6 --format="value(name)"
```
Expected: lists `openai-api-key`, `qdrant-api-key`, `db-password`.

(No commit — gcloud-only task.)

---

## Task 5: Build, push, and deploy the BACKEND

**Files:** none (build + gcloud).

- [ ] **Step 1: Tag + push the backend image to Artifact Registry**

```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
REG=us-central1-docker.pkg.dev/cobalt-bond-494609-a6/car-recsys
docker tag car-backend:latest $REG/backend:latest
docker push $REG/backend:latest 2>&1 | tail -3
```
Expected: `latest: digest: sha256:...` (push succeeds; auth was configured earlier
via `gcloud auth configure-docker us-central1-docker.pkg.dev`).

- [ ] **Step 2: Deploy backend (CORS still open: ENVIRONMENT not set to production)**

The DATABASE_URL uses the Cloud SQL unix-socket form. The `${DB_PASSWORD}` is
substituted by Cloud Run from the secret via `--update-secrets` does NOT interpolate
into other env vars — so build the DSN WITHOUT the password and instead rely on the
socket + a password-carrying secret is not directly composable. Use the full DSN with
the password inline via a dedicated secret-backed env is not possible. Therefore: put
the WHOLE DATABASE_URL in a secret too (simplest, password not in plaintext flags).

First create the DATABASE_URL secret (socket form, with password):
```bash
P=--project=cobalt-bond-494609-a6
INST=cobalt-bond-494609-a6:us-central1:free-trial-first-project
printf '%s' "postgresql+psycopg2://admin:admin123@/car_recsys?host=/cloudsql/$INST" \
  | gcloud secrets create database-url --data-file=- $P
SA="$(gcloud projects describe cobalt-bond-494609-a6 --format='value(projectNumber)')-compute@developer.gserviceaccount.com"
gcloud secrets add-iam-policy-binding database-url \
  --member="serviceAccount:$SA" --role="roles/secretmanager.secretAccessor" --project=cobalt-bond-494609-a6
```

Then deploy:
```bash
REG=us-central1-docker.pkg.dev/cobalt-bond-494609-a6/car-recsys
gcloud run deploy car-backend \
  --image=$REG/backend:latest \
  --region=us-central1 \
  --project=cobalt-bond-494609-a6 \
  --platform=managed \
  --allow-unauthenticated \
  --add-cloudsql-instances=cobalt-bond-494609-a6:us-central1:free-trial-first-project \
  --set-env-vars=QDRANT_URL=https://ace7f34a-eb29-4ae5-9454-707191cc9612.us-east4-0.gcp.cloud.qdrant.io:6333,QDRANT_COLLECTION=car_chatbot_vectors \
  --set-secrets=DATABASE_URL=database-url:latest,OPENAI_API_KEY=openai-api-key:latest,QDRANT_API_KEY=qdrant-api-key:latest \
  --memory=1Gi --cpu=1 --min-instances=0 --max-instances=2
```

- [ ] **Step 3: Capture backend URL**

```bash
BACKEND_URL=$(gcloud run services describe car-backend --region=us-central1 \
  --project=cobalt-bond-494609-a6 --format='value(status.url)')
echo "BACKEND_URL=$BACKEND_URL"
```
Save this URL — Task 6 needs it.

- [ ] **Step 4: Verify backend health + DB**

```bash
curl -s -o /dev/null -w "docs:%{http_code}\n" "$BACKEND_URL/docs"
curl -s "$BACKEND_URL/api/v1/listings?limit=3" | head -c 300; echo
```
Expected: `docs:200`, and the listings call returns JSON with vehicles from Cloud
SQL (5318 backfilled). If listings 500s, `gcloud run services logs read car-backend
--region=us-central1 --project=cobalt-bond-494609-a6 --limit=30` — likely the
DATABASE_URL socket form or the Cloud SQL instance attach.

(No git commit — deploy step.)

---

## Task 6: Build, push, deploy the FRONTEND + tighten CORS

**Files:** none (build + gcloud).

- [ ] **Step 1: Build frontend with the real backend URL**

```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot/car-recsys-system/frontend
# BACKEND_URL from Task 5 Step 3:
docker build --build-arg VITE_API_URL="$BACKEND_URL" -t car-frontend:latest . 2>&1 | tail -3
REG=us-central1-docker.pkg.dev/cobalt-bond-494609-a6/car-recsys
docker tag car-frontend:latest $REG/frontend:latest
docker push $REG/frontend:latest 2>&1 | tail -3
```
Expected: build + push succeed.

- [ ] **Step 2: Deploy frontend**

```bash
REG=us-central1-docker.pkg.dev/cobalt-bond-494609-a6/car-recsys
gcloud run deploy car-frontend \
  --image=$REG/frontend:latest \
  --region=us-central1 \
  --project=cobalt-bond-494609-a6 \
  --platform=managed \
  --allow-unauthenticated \
  --memory=256Mi --cpu=1 --min-instances=0 --max-instances=2
FRONTEND_URL=$(gcloud run services describe car-frontend --region=us-central1 \
  --project=cobalt-bond-494609-a6 --format='value(status.url)')
echo "FRONTEND_URL=$FRONTEND_URL"
```

- [ ] **Step 3: Tighten backend CORS to the frontend URL**

Now restrict CORS by setting production env + the real origin (re-uses the same
image; just updates env, triggers a new revision):
```bash
gcloud run services update car-backend \
  --region=us-central1 --project=cobalt-bond-494609-a6 \
  --update-env-vars=ENVIRONMENT=production,BACKEND_CORS_ORIGINS="[\"$FRONTEND_URL\"]"
```
> Note: `BACKEND_CORS_ORIGINS` is a pydantic `List[str]`. pydantic-settings parses a
> JSON-array string from the env var. The value above is a JSON array with one URL.
> If pydantic rejects it at startup, fall back to leaving `ENVIRONMENT` unset (CORS
> stays permissive) — capture this in the deploy doc as a known caveat.

- [ ] **Step 4: End-to-end verification (external access)**

```bash
echo "Open in a browser (ideally another network/device): $FRONTEND_URL"
curl -s -o /dev/null -w "frontend:%{http_code}\n" "$FRONTEND_URL"
# CORS preflight check from the frontend origin:
curl -s -o /dev/null -w "cors:%{http_code}\n" -X OPTIONS \
  -H "Origin: $FRONTEND_URL" -H "Access-Control-Request-Method: GET" \
  "$BACKEND_URL/api/v1/listings?limit=1"
```
Expected: `frontend:200`, `cors:200`. Then in the browser: open `$FRONTEND_URL`,
confirm the home/search pages load vehicles and there are no CORS errors in the
console. Chatbot works only if embeddings exist in Qdrant Cloud (may be empty until
the ML embed runs — acceptable per spec).

(No git commit — deploy step.)

---

## Task 7: Document the deployment

**Files:**
- Create: `docs/cloud-run-deploy.md`

- [ ] **Step 1: Write the deploy runbook**

Create `docs/cloud-run-deploy.md` capturing: the two service names + URLs, the
deploy commands (Tasks 5–6), the secrets used, the DATABASE_URL socket form, how to
redeploy after a code change (rebuild image → push → `gcloud run deploy`), and the
CORS caveat from Task 6 Step 3. Keep secrets OUT (placeholders only), mirroring the
style of `docs/cloud-sql.md` / `docs/vm-worker.md`.

- [ ] **Step 2: Verify no secrets in the doc + commit**

```bash
cd /home/duc-nguyen16/car-recsys-consultant-chatbot
grep -cE "sk-proj-[A-Za-z]|admin123|eyJhbGci" docs/cloud-run-deploy.md   # expect 0
git add docs/cloud-run-deploy.md
git commit -m "docs: Cloud Run deployment runbook"
```

---

## Self-Review Notes

- **Spec coverage:** Qdrant api_key (T1), prod Dockerfile/$PORT (T2), prod CORS (T2,T6), frontend nginx multi-stage (T3), Cloud SQL Connector socket (T5 via DATABASE_URL secret + `--add-cloudsql-instances`), Secret Manager (T4,T5), backend-first deploy resolving the CORS↔VITE_API_URL cycle (T5 open → T6 tighten), Redis dropped (no task needed — code never used it), verification (T5,T6), docs (T7). All spec sections mapped.
- **Deviation from spec, intentional:** the spec sketched `DATABASE_URL` as a plain `--set-env-vars`; the plan puts the full socket DSN in a `database-url` secret instead, because the password belongs in Secret Manager and Cloud Run can't interpolate a password secret into a composed env var. Documented in T5 Step 2.
- **Placeholder scan:** secret VALUES are `<...>` by necessity (user-supplied); every command and code edit is concrete. No TODO/TBD.
- **Type consistency:** `QDRANT_API_KEY` (config) used identically at both call sites as `settings.QDRANT_API_KEY or None`. `$PORT`/8080 consistent across backend Dockerfile, frontend Dockerfile, and nginx.conf.
