#!/bin/sh
set -e

# Dokploy may mount /app/data as a named volume or a bind mount. When it is a
# bind mount the directory is owned by root, so fix ownership and then drop
# privileges to the unprivileged appuser before doing anything else.
if [ "$(id -u)" = "0" ]; then
    mkdir -p /app/data
    chown -R appuser:appuser /app/data
    exec gosu appuser "$0" "$@"
fi

# Dokploy runs the app and the database as separate services. With AUTO_INIT=true
# this entrypoint waits for Postgres, fetches the corpus if it is missing, and
# builds the schema/index on the first boot. Later restarts skip the expensive
# embedding step because the articles table is already populated.
if [ "${AUTO_INIT:-false}" = "true" ]; then
    echo "[entrypoint] AUTO_INIT=true - preparing database..."

    echo "[entrypoint] waiting for Postgres..."
    python - <<'PY'
import sys
import time

import psycopg

from metascholar.config import settings

for attempt in range(30):
    try:
        psycopg.connect(**settings.get_postgres_kwargs()).close()
        print("[entrypoint] Postgres is ready.", flush=True)
        sys.exit(0)
    except Exception as exc:
        print(f"[entrypoint]   not ready ({exc}); retrying in 2s...", flush=True)
        time.sleep(2)

print("[entrypoint] Postgres did not become ready in time.", flush=True)
sys.exit(1)
PY

    corpus="${CORPUS_PATH:-data/corpus.jsonl}"
    if [ ! -s "$corpus" ]; then
        echo "[entrypoint] corpus missing, fetching from PubMed..."
        python -m metascholar.ingest.fetch_data
    fi

    if python - <<'PY'
import sys

import psycopg

from metascholar.config import settings

try:
    with psycopg.connect(**settings.get_postgres_kwargs()) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.articles')")
            if cur.fetchone()[0] is not None:
                cur.execute("SELECT COUNT(*) FROM articles")
                sys.exit(0 if cur.fetchone()[0] > 0 else 1)
except Exception as exc:
    print(f"[entrypoint] index check failed: {exc}", flush=True)
sys.exit(1)
PY
    then
        echo "[entrypoint] corpus already indexed, skipping init."
    else
        echo "[entrypoint] articles table empty - initializing schema and embedding corpus..."
        python -m metascholar.database.db_init
    fi
fi

exec "$@"
