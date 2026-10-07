PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS source_docs (
  source_id       TEXT PRIMARY KEY,
  source_type     TEXT NOT NULL,
  provider        TEXT NOT NULL,
  title           TEXT NOT NULL,
  published_at    TEXT NOT NULL,
  url             TEXT NOT NULL,
  text            TEXT NOT NULL,
  ingested_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS macro_signals (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id       TEXT NOT NULL,
  extracted_at_utc TEXT NOT NULL,
  signal_json     TEXT NOT NULL,
  FOREIGN KEY(source_id) REFERENCES source_docs(source_id)
);

CREATE INDEX IF NOT EXISTS idx_macro_signals_source_id
ON macro_signals(source_id);

CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  ts_utc TEXT NOT NULL,
  n_docs INTEGER NOT NULL,
  n_issues INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS issues (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  issue_type TEXT NOT NULL,
  source_id TEXT,
  details_json TEXT NOT NULL,
  ts_utc TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES runs(run_id)
);
