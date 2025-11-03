{{ config(
  materialized='table',
  partition_by={'field': 'created_date', 'data_type': 'date'}
) }}

WITH base AS (
  SELECT * FROM {{ ref('stg_reddit_posts') }}
),
tokens AS (
  SELECT
    reddit_id,
    created_date,
    engagement,
    title,
    selftext,
    token AS ticker
  FROM base,
  UNNEST(REGEXP_EXTRACT_ALL(UPPER(CONCAT(title, ' ', selftext)), r'\\b[A-Z]{1,5}\\b')) AS token
),
labeled AS (
  SELECT
    reddit_id,
    created_date,
    ticker,
    engagement,
    {{ calculate_sentiment_label("concat(title, ' ', selftext)") }} AS sentiment_label,
    {{ sentiment_score_from_label(calculate_sentiment_label("concat(title, ' ', selftext)")) }} AS sentiment_score
  FROM tokens
)
SELECT * FROM labeled
;