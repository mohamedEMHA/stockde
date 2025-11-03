{% macro calculate_sentiment_label(text_expr) %}
(
  CASE
    WHEN REGEXP_CONTAINS(LOWER({{ text_expr }}), r'\\bbullish\\b|\\bbuy\\b|\\brally\\b|\\bmooning\\b') THEN 'POSITIVE'
    WHEN REGEXP_CONTAINS(LOWER({{ text_expr }}), r'\\bbearish\\b|\\bsell\\b|\\bcrash\\b|\\bpanic\\b') THEN 'NEGATIVE'
    ELSE 'NEUTRAL'
  END
)
{% endmacro %}

{% macro sentiment_score_from_label(label_expr) %}
(
  CASE
    WHEN {{ label_expr }} = 'POSITIVE' THEN 1.0
    WHEN {{ label_expr }} = 'NEGATIVE' THEN -1.0
    ELSE 0.0
  END
)
{% endmacro %}