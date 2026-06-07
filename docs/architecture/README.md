# Architecture Diagrams

Sơ đồ kiến trúc Car Recommendation System.

> **Dùng [diagrams.md](diagrams.md)** — bản **Mermaid**, render trực tiếp trên GitHub với
> đầy đủ label + màu. (Đã verify tất cả render ra SVG hợp lệ.)

| # | Diagram | Link |
|---|---------|------|
| 1 | Kiến trúc tổng thể (**local dev** — host crawler + Docker stack) | [diagrams.md](diagrams.md#1-kiến-trúc-tổng-thể-local-dev) |
| 2 | Temporal pipeline (WeeklyPipeline chain) | [diagrams.md](diagrams.md#2-temporal-pipeline--weeklypipeline) |
| 3 | dbt medallion (bronze→silver→gold) | [diagrams.md](diagrams.md#3-dbt-medallion--data-flow) |
| 4 | Recommendation engine | [diagrams.md](diagrams.md#4-recommendation-engine-multi-stage-hybrid) |
| 5 | Chatbot — **agentic LangGraph (v2)** | [diagrams.md](diagrams.md#5-chatbot--agentic-langgraph-chatbot-v2) |
| 6 | **Silver ERD** (3NF, đầy đủ cột + PK/FK) | [diagrams.md](diagrams.md#6-silver--erd-3nf-dimensional) |
| 7 | **Gold ERD** (app marts, vehicle_id) | [diagrams.md](diagrams.md#7-gold--erd-app-marts-denormalized) |
| 8 | **Reco / App-domain ERD** (users · interactions · item_similarity · chat · Qdrant) | [diagrams.md](diagrams.md#8-recommendation--app-domain-erd) |
| 9 | **Production deployment (GCP)** — AlloyDB · Cloud Run · Temporal Cloud · Qdrant Cloud | [diagrams.md](diagrams.md#9-production-deployment-gcp) |
