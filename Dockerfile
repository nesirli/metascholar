FROM python:3.12-slim

# make: so `make get_data` / `make init` can be run inside the container
# after deployment. uv: dependency management.
RUN apt-get update \
    && apt-get install -y --no-install-recommends make \
    && rm -rf /var/lib/apt/lists/* \
    && pip install uv

WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml ./
RUN uv venv && uv pip install -r pyproject.toml

COPY . .

# Install the metascholar package itself (deps already cached above).
# Without this, `import metascholar` fails at runtime.
RUN uv pip install --no-deps .

# The corpus is fetched after deployment by running `make get_data` inside the
# container (the build network cannot reach NCBI). It lands in /app/data, which
# should be a persistent volume so it survives restarts.

# Make the Makefile use the already-installed venv (no uv re-sync at runtime).
ENV PYTHON=python
ENV STREAMLIT=streamlit

# Railway injects PORT at runtime. Locally we default to 8501.
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0

EXPOSE 8501

# Streamlit serves its health endpoint under the baseUrlPath, so include ROOT_PATH.
# On Railway the app listens on $PORT; locally it falls back to STREAMLIT_SERVER_PORT.
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
    CMD python -c "import os,urllib.request,sys; p=os.environ.get('ROOT_PATH',''); port=os.environ.get('PORT',os.environ.get('STREAMLIT_SERVER_PORT','8501')); sys.exit(0 if urllib.request.urlopen(f'http://localhost:{port}{p}/_stcore/health',timeout=2).status==200 else 1)"

CMD ["sh", "-c", "streamlit run src/metascholar/app/app.py --server.port=${PORT:-$STREAMLIT_SERVER_PORT} --server.address=$STREAMLIT_SERVER_ADDRESS --server.baseUrlPath=${ROOT_PATH:-} --server.enableXsrfProtection=false --server.enableCORS=false --server.headless=true"]
