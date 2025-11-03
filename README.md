# Reddit Stock Sentiment Data-Engineering Pipeline

![CI](https://img.shields.io/github/actions/workflow/status/your-org/your-repo/ci.yml?label=dbt%20build)
![Terraform Plan](https://img.shields.io/badge/Terraform%20plan-clean-brightgreen)
![Looker](https://img.shields.io/badge/Looker-dashboard%20live-blue)

## Table of Contents
- Overview
- Features (Milestones)
- Quick Start (Local)
- Structure
- Terraform (GCP)
- Airflow DAGs
- Tech Stack
- Security
- M3 — dbt Transformation
- M4 — Visualization & CI/CD
- Architecture & Cost

This repository upgrades a single Python script into a full Data Engineering portfolio project that demonstrates ingestion → transformation → serving → orchestration → visualization.

## Features (Milestones)
- M1: Repo bootstrap, Terraform skeleton, Airflow skeleton with Docker Compose.
- M2: Ingestion DAG using official Reddit API, raw landing in GCS (Parquet), Great Expectations checkpoint.
- M3: dbt transformations (staging + marts), tests, docs on GitHub Pages.
- M4: Looker Studio dashboard, CI/CD (GitHub Actions), short walkthrough video.

## Quick Start (Local)
1. Install Docker Desktop and enable Linux containers.
2. Copy `.env.example` to `.env` and fill values as needed.
3. Start Airflow locally:
   - `make airflow-init`
   - `make up`
   - Open `http://localhost:8080` (user: `admin`, password: `admin`)

## Structure
- `docker-compose.yml`: Local Airflow stack (webserver, scheduler, Postgres).
- `dags/`: Airflow DAGs (e.g., `dag_ingest_reddit`, `dag_dbt_run_and_test`).
- `terraform/`: GCP IaC for bucket (raw landing), BigQuery dataset, Composer (optional), Secret Manager.
- `transform/`: dbt project skeleton (to be completed in M3).
- `transform/`: dbt project (staging + marts, tests, docs).
- `docs/`: Architecture diagram placeholders.
- `Makefile`: Common commands.
- `.pre-commit-config.yaml`: Black, Flake8.

## Terraform (GCP)
Configure your GCP credentials locally (e.g., via `gcloud auth application-default login`).

```
make terraform-init
make terraform-plan
```

By default `composer` creation is disabled; enable by setting `TF_VAR_enable_composer=true`.

## Airflow DAGs
- `dag_ingest_reddit`: Hourly ingestion skeleton.
- `dag_ingest_reddit.load_gcs_to_bq`: Μετατροπή `.jsonl.snappy` → `.jsonl.gz` και BigQuery load (WRITE_TRUNCATE σε ημερήσιο partition).
- `dag_dbt_run_and_test`: Hourly; waits on `dag_ingest_reddit.load_gcs_to_bq`, then runs `dbt build`.

## Tech Stack
- Python 3.11 (Airflow image)
- Docker & Docker Compose
- Terraform (GCP)
- Apache Airflow (Cloud Composer optional)
- GCS + BigQuery
- dbt-core
- Great Expectations + Elementary (later milestone)
- HuggingFace (sentiment), spaCy/Flair (NER) in later milestones

## Security
- No secrets committed. Use environment variables and Secret Manager.

## License
MIT — see `LICENSE`.

## M3 — dbt Transformation
- Profile: `reddit_de` (targets: `dev` → dataset `dbt_dev`, `prod` → `reddit_marts`).
- Staging models:
  - `stg_reddit_posts` — cast `created_utc` to `TIMESTAMP/DATE`, dedup via `QUALIFY ROW_NUMBER()`, null cleaning.
  - `stg_tickers` — extract tickers via regex `\b[A-Z]{1,5}\b` from `title || selftext`, simple sentiment label (macro).
- Marts:
  - `mart_stock_mentions` — 1 row per `(ticker, date)` with `mentions`, `avg_sentiment`, `total_engagement`.
- Tests:
  - `reddit_id` uniqueness; `sentiment_label` accepted values; custom test `ticker_regex`.
- Docs: `dbt docs generate` published to GitHub Pages by CI.

Prereq: ensure a raw table exists in BigQuery as `reddit_stock_sentiment.raw_reddit_json` with columns used in `stg_reddit_posts`. For a quick bootstrap (empty table):

```
CREATE TABLE `${PROJECT_ID}.reddit_stock_sentiment.raw_reddit_json` (
  id STRING,
  subreddit STRING,
  title STRING,
  selftext STRING,
  ups INT64,
  num_comments INT64,
  engagement INT64,
  created_utc FLOAT64
);
```

Run dbt locally inside Airflow container (scheduled automatically):

```
dbt build --profiles-dir /opt/airflow/dbt --project-dir /opt/airflow/transform --target dev
```

## M4 — Visualization & CI/CD
- Looker Studio: connect to `reddit_marts.mart_stock_mentions` (prod target) and build:
  - Daily mentions volume (time series)
  - Top 10 tickers (pie)
  - Avg sentiment vs BTC closing price (join with `bigquery-public-data.crypto_bitcoin.price_daily`)
- Export a public share link and capture a screenshot to `docs/looker_screenshot.png`.
- GitHub Actions: see `.github/workflows/ci.yml` — lint, Terraform plan (comment on PR), `dbt build`, `dbt docs generate` → deploy to `gh-pages`.
- Walkthrough video: add `docs/walkthrough.mp4` and embed below.

### Walkthrough (Loom)
<video src="docs/walkthrough.mp4" controls width="640"></video>

### Looker Screenshot
![Looker Studio](docs/looker_screenshot.png)

## Architecture & Cost
- See `docs/architecture.png` for high-level diagram (GCS raw → BigQuery staging/marts → Looker, orchestrated by Airflow, provisioned by Terraform).
- Estimated monthly cost: < $5 for small footprint (1 GCS bucket, 1 BigQuery dataset with light daily loads, no Composer). Actuals vary; capture billing screenshot post `terraform apply`.