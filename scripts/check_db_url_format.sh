#!/usr/bin/env bash
cd /opt/worldcup-predictor
set -a && source .env.production && set +a
.venv/bin/python <<'PY'
import os
from urllib.parse import urlparse
url = os.environ.get("DATABASE_URL", "")
u = urlparse(url)
pw = u.password or ""
print(f"INFO\tpassword_len={len(pw)}")
print(f"INFO\tat_count_in_url={url.count('@')}")
print(f"INFO\thas_unencoded_specials={'#' in pw or '%' in url.split('@')[0][-20:]}")
if url.count("@") > 1:
    print("WARN\tMultiple @ in URL — password may need URL-encoding (%40 for @)")
PY
