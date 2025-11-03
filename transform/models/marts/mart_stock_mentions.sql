{{ config(
  materialized='table',
  partition_by={'field': 'date', 'data_type': 'date'}
) }}

WITH t AS (
  SELECT
    created_date AS date,
    ticker,
    sentiment_label,
    sentiment_score,
    engagement
  FROM {{ ref('stg_tickers') }}
)
SELECT
  ticker,
  date,
  COUNT(*) AS mentions,
  AVG(sentiment_score) AS avg_sentiment,
  SUM(engagement) AS total_engagement
FROM t
GROUP BY ticker, date
;