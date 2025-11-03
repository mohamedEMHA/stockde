{% test ticker_regex(model, column_name) %}
SELECT *
FROM {{ model }}
WHERE REGEXP_CONTAINS({{ column_name }}, r'^[A-Z]{1,5}$') IS FALSE
{% endtest %}