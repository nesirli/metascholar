# syntax=docker/dockerfile:1

# ---- build stage -------------------------------------------------------------
# Dependencies are resolved from the committed uv.lock so builds are reproducible.
# The project itself is installed after the sources are copied in.
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY . .
RUN uv sync --frozen --no-dev

# ---- runtime stage -----------------------------------------------------------
FROM python:3.12-slim AS runtime

# make: run `make get_data` / `make init` from Dokploy's terminal.
# gosu: drop from root to the unprivileged user after fixing volume ownership.
RUN apt-get update \
    && apt-get install -y --no-install-recommends make gosu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# The venv built above is copied in below; put it first on PATH.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHON=python \
    STREAMLIT=streamlit \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0

COPY --from=builder /app /app

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data \
    && chmod +x /app/docker-entrypoint.sh \
    && chown -R appuser:appuser /app

# The entrypoint starts as root, fixes ownership of the mounted /app/data
# volume, then re-executes itself as appuser via gosu.
EXPOSE 8501

# Streamlit serves its health endpoint under the base URL path, so include ROOT_PATH.
HEALTHCHECK --interval=30s --timeout=3s --start-period=60s --retries=3 \
    CMD python -c "import os,urllib.request,sys; p=os.environ.get('ROOT_PATH',''); port=os.environ.get('PORT',os.environ.get('STREAMLIT_SERVER_PORT','8501')); sys.exit(0 if urllib.request.urlopen(f'http://localhost:{port}{p}/_stcore/health',timeout=2).status==200 else 1)"

# Opt-in first-boot bootstrap (wait for Postgres, fetch corpus, build index).
# See docker-entrypoint.sh and AUTO_INIT in .env.example.
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Dokploy routes its domain to this container port. PORT/ROOT_PATH are honoured
# so the same image works behind a reverse proxy or under a sub-path.
CMD ["sh", "-c", "streamlit run src/metascholar/app/app.py --server.port=${PORT:-$STREAMLIT_SERVER_PORT} --server.address=$STREAMLIT_SERVER_ADDRESS --server.baseUrlPath=${ROOT_PATH:-} --server.enableXsrfProtection=false --server.enableCORS=false --server.headless=true"]
