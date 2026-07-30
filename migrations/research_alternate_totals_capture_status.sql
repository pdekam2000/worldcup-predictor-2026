-- Additive alternate totals capture status (shadow / infra)
CREATE TABLE IF NOT EXISTS alternate_totals_capture_status (
  status_id TEXT PRIMARY KEY,
  fixture_id INTEGER NOT NULL,
  line REAL NOT NULL,
  status TEXT NOT NULL,
  reason TEXT,
  created_at_utc TEXT NOT NULL
);
