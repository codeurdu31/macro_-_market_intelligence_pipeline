SELECT COUNT(*) FROM source_docs;

SELECT provider, COUNT(*) AS n
FROM source_docs
GROUP BY provider
ORDER BY n DESC;

SELECT source_id, extracted_at_utc
FROM macro_signals
ORDER BY extracted_at_utc DESC
LIMIT 10;
