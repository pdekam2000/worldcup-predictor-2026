#!/usr/bin/env bash
set -uo pipefail
cd /opt/worldcup-predictor
set -a
source .env.production
set +a
.venv/bin/python -c 'from sqlalchemy import create_engine; import os; create_engine(os.environ["DATABASE_URL"]).connect(); print("DB connection OK")'
.venv/bin/alembic upgrade head
echo "ALEMBIC_EXIT=$?"
