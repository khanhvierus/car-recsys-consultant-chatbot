# Pipeline Worker trên GCE VM + Temporal Cloud

Chạy `pipeline-worker` (Transform + ML) trên một **GCE VM** thay vì local, kết nối
**Temporal Cloud** (namespace `car-recsys.islko`) và **Cloud SQL**.

> Kiến trúc: VM (Docker) chạy worker → poll task từ Temporal Cloud → ghi Cloud SQL.
> Crawler vẫn chạy host (cần Chrome). Đây CHỈ là worker pipeline (no Chrome).

```
Temporal Cloud (car-recsys.islko.tmprl.cloud:7233, API key)
      ▲ poll task queue car-pipeline-tq
      │
GCE VM (e2-standard-2, us-central1-a)
  docker run pipeline-worker  ──► Cloud SQL (34.66.189.61, sslmode=require)
                              ──► GCS bucket (service account scope)
```

---

## Thành phần đã setup (✅ = xong)

- ✅ Temporal Cloud namespace `car-recsys.islko`, **API Key auth** (mTLS không
  dùng được vì namespace đã chốt API-key lúc tạo).
- ✅ Worker `client.py` hỗ trợ `TEMPORAL_API_KEY` (commit `1407f83`).
- ✅ Artifact Registry repo: `us-central1-docker.pkg.dev/cobalt-bond-494609-a6/car-recsys`
- ✅ Image đã push: `.../car-recsys/pipeline-worker:latest`
- ✅ VM `temporal-worker` chạy worker → **Connected** Temporal Cloud (poll `car-pipeline-tq`)
- ✅ VM IP đã trong Cloud SQL authorized network (connect tới được, chỉ cần đúng password)

---

## 1. Tạo API Key (Temporal Cloud)

cloud.temporal.io → avatar → **API Keys → Create**:
- Tên: `worker-key`, chọn thời hạn.
- Copy key `tmprl_...` (chỉ hiện 1 lần).

## 2. Tạo VM

```bash
gcloud compute instances create temporal-worker \
  --project=cobalt-bond-494609-a6 \
  --zone=us-central1-a \
  --machine-type=e2-standard-2 \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=20GB --boot-disk-type=pd-standard \
  --scopes=cloud-platform \
  --tags=temporal-worker
```

`--scopes=cloud-platform` → VM dùng service account mặc định để đọc GCS bucket
(load_bronze) mà không cần copy key.

### Lấy public IP của VM
```bash
gcloud compute instances describe temporal-worker \
  --zone=us-central1-a --project=cobalt-bond-494609-a6 \
  --format="value(networkInterfaces[0].accessConfigs[0].natIP)"
```

## 3. Cho VM connect Cloud SQL

Thêm **public IP của VM** vào authorized networks của Cloud SQL (GHI ĐÈ — phải
liệt kê cả IP nhà bạn nếu vẫn muốn connect từ local):
```bash
gcloud sql instances patch free-trial-first-project \
  --authorized-networks=<VM_IP>/32,171.253.158.82/32 \
  --project=cobalt-bond-494609-a6
```

> VM ephemeral IP đổi khi restart → phải patch lại. Muốn cố định: reserve static IP.

## 4. SSH vào VM + cài Docker

```bash
gcloud compute ssh temporal-worker --zone=us-central1-a --project=cobalt-bond-494609-a6

# --- trên VM ---
sudo apt-get update && sudo apt-get install -y docker.io
sudo usermod -aG docker $USER && newgrp docker      # dùng docker không cần sudo
# auth docker với Artifact Registry (VM service account đã có quyền):
gcloud auth configure-docker us-central1-docker.pkg.dev --quiet
```

## 5. Pull image + tạo env

```bash
# --- trên VM ---
IMG=us-central1-docker.pkg.dev/cobalt-bond-494609-a6/car-recsys/pipeline-worker:latest
docker pull $IMG

# file env (KHÔNG commit — chứa secret):
cat > worker.env <<'EOF'
TEMPORAL_ADDRESS=car-recsys.islko.tmprl.cloud:7233
TEMPORAL_NAMESPACE=car-recsys.islko
TEMPORAL_API_KEY=<dán API key tmprl từ Temporal Cloud>

WAREHOUSE_DSN=postgresql://admin:<PASS>@34.66.189.61:5432/car_recsys?sslmode=require
DBT_PG_HOST=34.66.189.61
DBT_PG_PORT=5432
DBT_PG_USER=admin
DBT_PG_PASSWORD=<PASS>
DBT_PG_DBNAME=car_recsys
DBT_PG_SSLMODE=require

GCS_BUCKET=incremental_raw
GCP_PROJECT_ID=cobalt-bond-494609-a6

OPENAI_API_KEY=<OpenAI key, để trống nếu chưa dùng>
# Qdrant Cloud (embed_vehicles). Để trống QDRANT_URL → bước embed tự skip.
QDRANT_URL=https://<cluster-id>.<region>.gcp.cloud.qdrant.io:6333
QDRANT_API_KEY=<Qdrant Cloud API key>
QDRANT_COLLECTION=car_chatbot_vectors
OPENAI_EMBEDDING_MODEL=text-embedding-3-large
OPENAI_EMBEDDING_DIM=3072
EOF
```

> **Qdrant**: image (commit `91cd2f0`) hỗ trợ `QDRANT_API_KEY` cho Qdrant Cloud.
> Nếu `QDRANT_URL` rỗng → `embed_vehicles` skip (không fail). Endpoint Qdrant
> Cloud thêm `:6333` (REST). Nhớ cập nhật image trên VM (`docker pull` + recreate)
> sau khi đổi worker.env.

> **⚠️ Thay password ở 2 CHỖ:** cả `WAREHOUSE_DSN` (dùng bởi load_bronze /
> ensure_partition / refresh_matviews qua psycopg2) VÀ `DBT_PG_PASSWORD` (dùng
> bởi dbt). Quên `<PASS>` trong WAREHOUSE_DSN → `ensure_partition` báo
> `password authentication failed for user "admin"`.
>
> **GCS auth trên VM:** image dùng `google.cloud.storage` → tự lấy credential từ
> metadata server của VM (scope cloud-platform). Không cần `GOOGLE_APPLICATION_CREDENTIALS`.
> Nhưng phải đảm bảo service account của VM có quyền đọc bucket (mặc định Compute
> SA thường có; nếu 403 thì grant `roles/storage.objectViewer`).

## 6. Run worker

```bash
# --- trên VM ---
docker run -d --name pipeline-worker --restart unless-stopped \
  --env-file worker.env \
  us-central1-docker.pkg.dev/cobalt-bond-494609-a6/car-recsys/pipeline-worker:latest

# xem log (phải thấy "Connected. Pipeline worker on task queue car-pipeline-tq")
docker logs -f pipeline-worker
```

## 7. Trigger workflow (từ local, trỏ Temporal Cloud)

```bash
# --- trên LOCAL ---
cd crawler
TEMPORAL_ADDRESS=car-recsys.islko.tmprl.cloud:7233 \
TEMPORAL_NAMESPACE=car-recsys.islko \
TEMPORAL_API_KEY=tmprl_... \
WAREHOUSE_DSN=postgresql://admin:<PASS>@34.66.189.61:5432/car_recsys?sslmode=require \
  PYTHONPATH=. .venv/bin/python -m temporal_app.scripts.trigger_once transform
```

Hoặc đăng ký schedule (create_schedule.py với cùng env Temporal Cloud).
Workflow chạy trên VM worker → hiện trên Temporal Cloud UI.

---

## Theo dõi worker (không phải kubectl — đây là VM Docker)

```bash
# SSH vào VM rồi:
docker ps                          # worker đang chạy?
docker logs -f pipeline-worker     # log realtime
docker stats pipeline-worker       # CPU/RAM usage

# từ local (không cần SSH):
gcloud compute ssh temporal-worker --zone=us-central1-a \
  --command="docker ps && docker logs --tail 20 pipeline-worker" \
  --project=cobalt-bond-494609-a6
```

> Bạn ban đầu muốn `kubectl get pod` — đó là Kubernetes. VM Docker dùng
> `docker ps`. Nếu sau này thực sự cần kubectl, phải lên GKE hoặc cài k3s trên VM.

---

## Cấu hình VM — vì sao e2-standard-2

| Activity | Tải | Ghi chú |
|---|---|---|
| `load_bronze` | network I/O (GCS) | nhẹ |
| `dbt_build` | CPU vừa + I/O Postgres | OK với 2 vCPU |
| `compute_item_similarity` | **RAM cao nhất** (sklearn cosine matrix) | 8GB đủ cho data hiện tại (5318 xe) |
| `embed_vehicles` | network (OpenAI API) | nhẹ |

`e2-standard-2` (2 vCPU / 8GB) cân bằng tốt. Data lớn dần → nâng `e2-standard-4`.

---

## Chi phí & dọn dẹp

```bash
# TẮT VM khi không dùng (không mất disk, không tính vCPU):
gcloud compute instances stop temporal-worker --zone=us-central1-a --project=cobalt-bond-494609-a6
gcloud compute instances start temporal-worker --zone=us-central1-a --project=cobalt-bond-494609-a6

# XÓA hẳn:
gcloud compute instances delete temporal-worker --zone=us-central1-a --project=cobalt-bond-494609-a6
```

- VM `e2-standard-2` ~$49/tháng nếu chạy 24/7. **Stop khi không dùng.**
- Artifact Registry tính theo storage (~$0.10/GB/tháng).
- Temporal Cloud: trial $1000, đang còn ~$738 / 12 ngày.

---

## ⚠️ Lưu ý

1. **Secret**: `worker.env` chứa API key + DB password — KHÔNG commit, chỉ ở VM.
2. **VM IP đổi** khi restart → patch lại Cloud SQL authorized network.
3. **GCS 403 trên VM**: grant service account của VM quyền đọc bucket:
   `gsutil iam ch serviceAccount:<VM_SA>:roles/storage.objectViewer gs://incremental_raw`
4. **Cập nhật image**: build + push lại từ local, rồi VM `docker pull` + recreate:
   ```bash
   # local
   docker build -f crawler/Dockerfile.pipeline -t car-pipeline-worker:latest .
   docker tag car-pipeline-worker:latest us-central1-docker.pkg.dev/cobalt-bond-494609-a6/car-recsys/pipeline-worker:latest
   docker push us-central1-docker.pkg.dev/cobalt-bond-494609-a6/car-recsys/pipeline-worker:latest
   # VM
   docker pull <IMG> && docker rm -f pipeline-worker && docker run -d ... (như bước 6)
   ```
