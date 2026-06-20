#!/usr/bin/env bash
# Grant worldcup_user DDL rights on public schema (PG 15+ fix). No data overwrite.
set -uo pipefail
sudo -u postgres psql -d worldcup_predictor -v ON_ERROR_STOP=1 <<'SQL'
GRANT ALL PRIVILEGES ON DATABASE worldcup_predictor TO worldcup_user;
GRANT CREATE, USAGE ON SCHEMA public TO worldcup_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO worldcup_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO worldcup_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO worldcup_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO worldcup_user;
SQL
echo "PASS	PostgreSQL schema grants applied"

cd /opt/worldcup-predictor
set -a && source .env.production && set +a
.venv/bin/alembic upgrade head
echo "ALEMBIC_EXIT=$?"
