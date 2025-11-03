import json
import os
import time
import random
import logging
from datetime import datetime, timezone

import pandas as pd
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable
from airflow.exceptions import AirflowFailException

try:
    import great_expectations as ge
except Exception:
    ge = None

try:
    from google.cloud import storage
except Exception:
    storage = None

try:
    from google.cloud import bigquery
except Exception:
    bigquery = None

try:
    import praw
    import prawcore
except Exception:
    praw = None
    prawcore = None

try:
    import snappy
except Exception:
    snappy = None


DEFAULT_SUBREDDITS = [
    'stocks', 'StockMarket', 'investing', 'SecurityAnalysis', 'wallstreetbets',
    'ValueInvesting', 'DividendInvesting', 'ETFs', 'options', 'pennystocks',
    'Daytrading', 'CanadianInvestor', 'UKInvesting', 'investingforbeginners',
    'Superstonk', 'algotrading', 'SPACs', 'RobinHoodPennyStocks', 'dividends'
]

POST_FETCH_LIMIT = int(Variable.get("post_fetch_limit", default_var=os.getenv("POST_FETCH_LIMIT", "50")))
MIN_ENGAGEMENT = int(Variable.get("min_engagement", default_var=os.getenv("MIN_ENGAGEMENT", "0")))


def _get_bucket_client():
    if storage is None:
        raise AirflowFailException("google-cloud-storage δεν είναι διαθέσιμο (package missing)")
    client = storage.Client()
    bucket_name = Variable.get("gcp_bucket", default_var=os.getenv("GCP_BUCKET"))
    if not bucket_name:
        raise AirflowFailException("Λείπει GCP bucket: ορίστε Airflow Variable 'gcp_bucket' ή env GCP_BUCKET")
    bucket = client.bucket(bucket_name)
    return bucket


def _load_manifest(bucket, ingest_date: str, hour: str):
    manifest_blob = bucket.blob(f"raw_reddit/_manifests/ingest_date={ingest_date}/hour={hour}/ids.txt")
    existing_ids = set()
    if manifest_blob.exists():
        s = manifest_blob.download_as_text(encoding="utf-8")
        for line in s.splitlines():
            line = line.strip()
            if line:
                existing_ids.add(line)
    return existing_ids, manifest_blob


def _save_manifest(manifest_blob, ids_set: set):
    lines = "\n".join(sorted(ids_set))
    manifest_blob.upload_from_string(lines, content_type="text/plain")


def extract_posts(**context):
    """Εξαγωγή posts από Reddit (PRAW), με απλό rate-limit/backoff και dedup στο batch."""
    creds = {
        "client_id": Variable.get("reddit_client_id", default_var=os.getenv("REDDIT_CLIENT_ID")),
        "client_secret": Variable.get("reddit_client_secret", default_var=os.getenv("REDDIT_CLIENT_SECRET")),
        "user_agent": Variable.get("reddit_user_agent", default_var=os.getenv("REDDIT_USER_AGENT")),
        "username": Variable.get("reddit_username", default_var=os.getenv("REDDIT_USERNAME")),
        "password": Variable.get("reddit_password", default_var=os.getenv("REDDIT_PASSWORD")),
    }

    subreddits_json = Variable.get("subreddits", default_var=None)
    subreddits = json.loads(subreddits_json) if subreddits_json else DEFAULT_SUBREDDITS

    if praw is None:
        raise AirflowFailException("PRAW δεν είναι εγκατεστημένο")

    try:
        reddit = praw.Reddit(
            client_id=creds["client_id"],
            client_secret=creds["client_secret"],
            user_agent=creds["user_agent"],
            username=creds["username"],
            password=creds["password"],
        )
    except Exception as e:
        raise AirflowFailException(f"Αποτυχία αρχικοποίησης PRAW: {e}")

    records = []
    for sr in subreddits:
        try:
            for post in reddit.subreddit(sr).hot(limit=POST_FETCH_LIMIT):
                engagement = getattr(post, "score", 0) + getattr(post, "num_comments", 0)
                if engagement < MIN_ENGAGEMENT or getattr(post, "stickied", False):
                    continue
                rec = {
                    "id": post.id,
                    "subreddit": post.subreddit.display_name,
                    "title": post.title,
                    "selftext": getattr(post, "selftext", "") or "",
                    "ups": getattr(post, "score", 0),
                    "num_comments": getattr(post, "num_comments", 0),
                    "engagement": engagement,
                    "permalink": f"https://reddit.com{getattr(post, 'permalink', '')}",
                    "created_utc": float(getattr(post, "created_utc", time.time())),
                }
                records.append(rec)
            time.sleep(random.uniform(1.5, 3.0))
        except Exception as e:
            if prawcore and isinstance(e, (prawcore.exceptions.Forbidden, prawcore.exceptions.NotFound)):
                logging.warning(f"Παράλειψη r/{sr}: {e}")
            elif prawcore and isinstance(e, prawcore.exceptions.TooManyRequests):
                delay = random.uniform(30, 90)
                logging.warning(f"Rate limited. Αναμονή {delay:.0f}s.")
                time.sleep(delay)
            else:
                logging.warning(f"Σφάλμα στο r/{sr}: {e}")
            continue

    # Dedup εντός batch
    seen = set()
    deduped = []
    for r in records:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        deduped.append(r)

    context["ti"].xcom_push(key="records", value=deduped)
    return len(deduped)


def validate_posts(**context):
    """Great Expectations checkpoint: schema, nulls, uniqueness, engagement >= 0."""
    records = context["ti"].xcom_pull(key="records", task_ids="extract_posts") or []
    if not records:
        logging.info("Χωρίς δεδομένα για validation.")
        return 0
    if ge is None:
        raise AirflowFailException("great_expectations δεν είναι διαθέσιμο")
    df = pd.DataFrame(records)
    ge_df = ge.dataset.PandasDataset(df)
    ge_df.expect_column_values_to_not_be_null("id")
    ge_df.expect_column_values_to_be_unique("id")
    ge_df.expect_column_values_to_be_between("engagement", min_value=0)
    # Απλές τύποι
    ge_df.expect_column_values_to_be_of_type("id", "str")
    ge_df.expect_column_values_to_be_of_type("subreddit", "str")
    ge_df.expect_column_values_to_be_of_type("title", "str")
    # ups & num_comments μπορεί να είναι int64/float — ελέγχουμε μόνο μη-αρνητικό
    result = ge_df.validate()
    if not result["success"]:
        raise AirflowFailException("Απέτυχε το Great Expectations validation")
    return len(records)


def load_to_gcs(**context):
    """Αποθήκευση raw JSONL σε GCS με Snappy compression και idempotency manifest."""
    records = context["ti"].xcom_pull(key="records", task_ids="extract_posts") or []
    if not records:
        logging.info("Δεν υπάρχουν νέα records για αποθήκευση.")
        return 0
    if snappy is None:
        raise AirflowFailException("python-snappy δεν είναι διαθέσιμο — δεν μπορώ να γράψω .jsonl.snappy")

    bucket = _get_bucket_client()
    now = datetime.now(timezone.utc)
    ingest_date = now.strftime("%Y-%m-%d")
    hour = now.strftime("%H")

    existing_ids, manifest_blob = _load_manifest(bucket, ingest_date, hour)
    new_records = [r for r in records if r["id"] not in existing_ids]
    if not new_records:
        logging.info("Idempotent skip: όλα τα ids υπάρχουν ήδη στο manifest.")
        return 0

    # JSONL + Snappy
    lines = [json.dumps(r, ensure_ascii=False) for r in new_records]
    jsonl_bytes = ("\n".join(lines)).encode("utf-8")
    compressed = snappy.compress(jsonl_bytes)

    prefix = f"raw_reddit/ingest_date={ingest_date}/hour={hour}/"
    filename = f"reddit_{int(time.time())}.jsonl.snappy"
    blob_path = prefix + filename
    blob = bucket.blob(blob_path)
    blob.upload_from_string(compressed, content_type="application/octet-stream")

    # Ενημέρωση manifest
    for r in new_records:
        existing_ids.add(r["id"])
    _save_manifest(manifest_blob, existing_ids)

    # XCom για το επόμενο βήμα (GCS→BQ)
    context["ti"].xcom_push(key="gcs_blob_path", value=blob_path)
    context["ti"].xcom_push(key="ingest_date", value=ingest_date)
    context["ti"].xcom_push(key="hour", value=hour)
    return len(new_records)


def load_gcs_to_bq(**context):
    """Μετατροπή .jsonl.snappy → .jsonl.gz και load στο BigQuery με WRITE_TRUNCATE στο ημερήσιο partition."""
    if bigquery is None:
        raise AirflowFailException("google-cloud-bigquery δεν είναι διαθέσιμο (package missing)")
    if storage is None:
        raise AirflowFailException("google-cloud-storage δεν είναι διαθέσιμο (package missing)")

    # Λήψη XCom από load_to_gcs
    ti = context["ti"]
    blob_path = ti.xcom_pull(key="gcs_blob_path", task_ids="load_to_gcs")
    ingest_date = ti.xcom_pull(key="ingest_date", task_ids="load_to_gcs")
    hour = ti.xcom_pull(key="hour", task_ids="load_to_gcs")
    if not blob_path or not ingest_date:
        logging.info("Δεν υπάρχει blob_path/ingest_date από το προηγούμενο task — παράλειψη.")
        return 0

    bucket = _get_bucket_client()
    src_blob = bucket.blob(blob_path)
    src_bytes = src_blob.download_as_bytes()

    # Decompress Snappy → GZIP
    import gzip as _gzip
    if snappy is None:
        raise AirflowFailException("python-snappy δεν είναι διαθέσιμο για αποσυμπίεση")
    jsonl_bytes = snappy.decompress(src_bytes)
    gz_bytes = _gzip.compress(jsonl_bytes)

    # Ανεβάζουμε το gzip σε διακριτό prefix για BigQuery loads
    bq_prefix = f"bq_json/ingest_date={ingest_date}/hour={hour}/"
    bq_filename = os.path.basename(blob_path).replace('.jsonl.snappy', '.jsonl.gz')
    bq_blob_path = bq_prefix + bq_filename
    bq_blob = bucket.blob(bq_blob_path)
    bq_blob.upload_from_string(gz_bytes, content_type="application/json")

    # BigQuery Load Job
    client = bigquery.Client()
    project_id = client.project
    dataset_id = Variable.get("bq_dataset", default_var=os.getenv("BQ_DATASET", "reddit_stock_sentiment"))
    table_id = f"{project_id}.{dataset_id}.raw_reddit_json"

    # Βεβαίωση ύπαρξης πίνακα και partitioning by ingestion time
    schema = [
        bigquery.SchemaField("id", "STRING"),
        bigquery.SchemaField("subreddit", "STRING"),
        bigquery.SchemaField("title", "STRING"),
        bigquery.SchemaField("selftext", "STRING"),
        bigquery.SchemaField("ups", "INTEGER"),
        bigquery.SchemaField("num_comments", "INTEGER"),
        bigquery.SchemaField("engagement", "INTEGER"),
        bigquery.SchemaField("created_utc", "FLOAT"),
    ]
    try:
        client.get_table(table_id)
    except Exception:
        tbl = bigquery.Table(table_id, schema=schema)
        tbl.time_partitioning = bigquery.TimePartitioning(type_=bigquery.TimePartitioningType.DAY)
        client.create_table(tbl)

    # Φόρτωση στο ημερήσιο partition με WRITE_TRUNCATE
    yyyymmdd = ingest_date.replace('-', '')
    destination = f"{table_id}${yyyymmdd}"
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        schema=schema,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    bucket_name = bucket.name
    uri = f"gs://{bucket_name}/{bq_blob_path}"
    job = client.load_table_from_uri(uri, destination=destination, job_config=job_config)
    result = job.result()
    logging.info(f"BigQuery load job ολοκληρώθηκε: {result.state}, destination={destination}")
    return 1


with DAG(
    dag_id="dag_ingest_reddit",
    default_args={"owner": "airflow"},
    schedule_interval="@hourly",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["ingestion", "reddit"],
) as dag:
    extract = PythonOperator(
        task_id="extract_posts",
        python_callable=extract_posts,
    )
    validate = PythonOperator(
        task_id="validate_posts",
        python_callable=validate_posts,
    )
    load = PythonOperator(
        task_id="load_to_gcs",
        python_callable=load_to_gcs,
    )
    load_bq = PythonOperator(
        task_id="load_gcs_to_bq",
        python_callable=load_gcs_to_bq,
    )

    extract >> validate >> load >> load_bq