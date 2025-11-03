{{ config(
  materialized='table',
  partition_by={'field': 'created_date', 'data_type': 'date'}
) }}

WITH raw AS (
  SELECT
    CAST(id AS STRING) AS reddit_id,
    subreddit,
    COALESCE(title, '') AS title,
    COALESCE(selftext, '') AS selftext,
    CAST(ups AS INT64) AS ups,
    CAST(num_comments AS INT64) AS num_comments,
    CAST(engagement AS INT64) AS engagement,
    CAST(created_utc AS FLOAT64) AS created_utc
  FROM {{ source('reddit', 'raw_posts') }}
),
dedup AS (
  SELECT *
  FROM raw
  QUALIFY ROW_NUMBER() OVER (PARTITION BY reddit_id ORDER BY created_utc DESC) = 1
)
SELECT
  reddit_id,
  subreddit,
  title,
  selftext,
  ups,
  num_comments,
  engagement,
  TIMESTAMP_SECONDS(CAST(created_utc AS INT64)) AS created_ts,
  DATE(TIMESTAMP_SECONDS(CAST(created_utc AS INT64))) AS created_date
FROM dedup
;