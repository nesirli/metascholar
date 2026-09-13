# MetaScholar

> RAG-based question answering over the metagenomics & microbiome literature. Ask a question, get an answer grounded in PubMed abstracts, with citations.

![Python](https://img.shields.io/badge/python-3.12%2B-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)
![Postgres](https://img.shields.io/badge/PostgreSQL%20%2B%20pgvector-336791?logo=postgresql&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)

## 🔗 Live demo

**https://metascholar.nasirnesirli.com**

| | |
|---|---|
| **Username** | `demo` |
| **Password** | `metascholar2026` |

> A public demo with shared credentials, so please don't rely on it for anything private.

---

## What it does

MetaScholar answers natural-language questions about metagenomics and microbiome research. Instead of relying on what a language model happens to have memorized, it:

1. **Retrieves** relevant PubMed abstracts from a local corpus (keyword + vector + hybrid search),
2. **Grounds** an LLM's answer in that retrieved context, and
3. **Returns** the answer with numbered source citations, so every claim is traceable back to a paper.

Every answer is also scored by an **LLM-as-a-judge** for relevance, and users can thumbs-up/down. Cost, latency, tokens, relevance, and feedback are all tracked on a built-in **dashboard**.

## Features

- **Grounded answers with citations:** responses cite `[1]`, `[2]`… mapped to PMIDs, titles, journals, and years. If the context doesn't contain the answer, it says "I don't know" rather than hallucinating.
- **Hybrid retrieval:** keyword search + pgvector semantic search, fused with Reciprocal Rank Fusion (RRF).
- **Automatic evaluation:** each answer is judged for relevance at query time and stored.
- **Dashboard:** total conversations, average latency, total cost, average tokens, cost/latency over time, relevance breakdown, and user-feedback stats.
- **Chat history:** sidebar with clickable past conversations and a "New chat" button.

## How it works

```
                                 ┌──────────── keyword search (token overlap)
  question ─► retrieve ──────────┤                                            ├─► RRF fuse ─► top-k context
                                 └──────────── vector search (pgvector cosine)
                                                          │
                                                          ▼
                     build prompt (context + question) ─► LLM (gpt-4o-mini) ─► cited answer
                                                          │
                                                          ▼
                                          LLM-as-a-judge scores relevance ─► stored + shown
```

- **Corpus:** ~9,900 PubMed abstracts on metagenomics/microbiome, fetched via NCBI E-utilities and stored as `data/corpus.jsonl`.
- **Embeddings:** OpenAI `text-embedding-3-small` (1536-dim), stored in Postgres with an HNSW index (`pgvector`).
- **Retrieval:** keyword (token-overlap scoring), vector (cosine similarity), and hybrid (RRF, `k=60`), with hybrid as the default.
- **Generation & judging:** OpenAI `gpt-4o-mini`.

## Tech stack

| Layer | Tool |
|---|---|
| UI | Streamlit |
| LLM & embeddings | OpenAI API (`gpt-4o-mini`, `text-embedding-3-small`) |
| Vector store | PostgreSQL + `pgvector` (HNSW, cosine) |
| Corpus ingest | PubMed E-utilities via `httpx` → JSONL |
| Config | `pydantic-settings` |
| Packaging | `uv` |
| Deployment | Docker + Dokploy |

## Getting started

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Docker (for Postgres + pgvector locally)
- An OpenAI API key

### 1. Install & configure

```bash
git clone https://github.com/nesirli/meta-scholar.git metascholar
cd metascholar
uv sync                      # install dependencies into .venv
cp .env.example .env         # then fill in OPENAI_API_KEY (defaults are fine for local)
```

`.env` values:

```
OPENAI_API_KEY=sk-...
POSTGRES_HOST=localhost
POSTGRES_DB=metascholar
POSTGRES_USER=user
POSTGRES_PASSWORD=password
APP_USERNAME=admin
APP_PASSWORD=password
```

### 2. Start Postgres (pgvector)

```bash
docker run -d --name metascholar-postgres \
  -e POSTGRES_DB=metascholar \
  -e POSTGRES_USER=user \
  -e POSTGRES_PASSWORD=password \
  -p 5432:5432 \
  -v metascholar-pgdata:/var/lib/postgresql/data \
  pgvector/pgvector:pg17
```

### 3. Fetch the corpus and build the index

```bash
make get_data     # fetch PubMed abstracts → data/corpus.jsonl
make init         # create the schema, embed abstracts into Postgres
```

`make init` embeds every abstract via the OpenAI API, so it makes ~9,900 calls (cheap, but takes a few minutes). It's idempotent, so it's safe to re-run.

### 4. Run the app

```bash
make run_app      # http://localhost:8501
```

Log in with the `APP_USERNAME` / `APP_PASSWORD` from your `.env`.

## Evaluation

Retrieval quality and prompt choices are measured, not guessed. Run:

```bash
make evaluate
```

This runs three evaluations and prints the estimated OpenAI cost at the end.

### 1. Retrieval comparison (keyword vs. vector)

For 10 representative queries it runs both keyword and vector search (top-5 each) and reports how much they **overlap**:

```
Query                                               Keyword   Vector  Overlap
------------------------------------------------------------------------------
What computational pipelines are used for metage..        5        5        0
How does diet affect the gut microbiome?                  5        5        0
...
------------------------------------------------------------------------------
AVERAGE                                                 5.0      5.0

Across all queries:
  Found by both:     1
  Keyword only:      47
  Vector only:       48
  Total unique:      96
```

The takeaway: keyword and vector search find **almost entirely different documents** (overlap is close to 0). That is the main argument for **hybrid search**. Combining both methods via RRF surfaces papers that neither method finds alone. That is why hybrid is the default retriever.

### 2. Search quality with Hit Rate and MRR

The evaluation also scores keyword, vector, and hybrid search with two standard retrieval metrics from the course repo:

- **Hit Rate**: the share of queries where the expected paper appears anywhere in the top-5 results.
- **MRR (Mean Reciprocal Rank)**: how high up the expected paper appears. A hit at rank 1 scores 1.0, rank 2 scores 0.5, rank 5 scores 0.2.

These metrics need a ground-truth file of `(question, pmid)` pairs. Generate it once from the corpus:

```bash
uv run python -m metascholar.rag.evaluate --generate-ground-truth
```

Then `make evaluate` will print a scorecard like this:

```
Method        Hit Rate        MRR
--------------------------------
keyword        0.350        0.280
vector         0.420        0.310
hybrid         0.550        0.460
```

### 3. Prompt A/B test (LLM-as-a-judge)

Two system-prompt variants, **Concise** vs. **Detailed**, are run over 5 queries. Each answer is graded by an LLM judge (`judge.py`) that classifies relevance as `RELEVANT` / `PARTLY_RELEVANT` / `NON_RELEVANT`, scored 2 / 1 / 0:

```
Results:
  Concise: 10/10 (100%)
  Detailed: 10/10 (100%)

Winner: Concise
Estimated generation cost: $0.0032
```

The judge returns a structured verdict (`relevance` + `explanation`) via OpenAI structured outputs, so scoring is consistent and parseable. It also retries automatically on transient failures, so the evaluation is more reliable.

### One-off end-to-end check

```bash
make test_rag     # run one query, print the cited answer + model, latency, tokens
```

### Continuous, in-app evaluation

The same judge runs **live**: every answer in the app is scored for relevance and stored, alongside user 👍/👎 feedback. The **Dashboard** tab aggregates relevance rates, user feedback, cost, latency, and token usage over time, so quality is monitored in production, not just offline.

### Unit tests

```bash
uv run pytest     # corpus parsing + RAG retrieval/context/prompt tests
```

## Makefile commands

| Command | What it does |
|---|---|
| `make get_data` | Fetch & parse PubMed abstracts → `data/corpus.jsonl` |
| `make init` | Create the DB schema and embed the corpus into Postgres |
| `make run_app` | Launch the Streamlit app |
| `make test_rag` | Run one end-to-end query and print the cited answer |
| `make evaluate` | Retrieval comparison + prompt A/B evaluation + Hit Rate/MRR if ground truth exists |
| `uv run python -m metascholar.rag.evaluate --generate-ground-truth` | Build a `(question, pmid)` ground-truth file from the corpus |

## Deployment

The repo ships a single `Dockerfile` and no Compose file, so it deploys as a
normal **Application** on a self-hosted [Dokploy](https://dokploy.com) instance,
with Postgres + pgvector running as a separate Dokploy **Database** service.

### Prerequisites

- A running Dokploy instance with a domain pointed at it.
- A Git provider connected to Dokploy (GitHub, GitLab, Gitea, …) or a public repo URL.
- An OpenAI API key.

### 1. Create the Postgres + pgvector database

1. In your Dokploy project: **Create Service → Database → PostgreSQL**.
2. Name it e.g. `metascholar-db` and create it.
3. Open the database → **Advanced → Custom Docker Image** and set it to
   `pgvector/pgvector:pg17` (the stock Postgres image does not include the
   `pgvector` extension). Save and redeploy the database.
4. Open **Connection** and copy the **Internal Connection URL**
   (`postgres://user:password@metascholar-db:5432/...`). You'll need it in step 3.

### 2. Create the application

1. In the same project: **Create Service → Application**.
2. Connect the Git provider / repo and pick the branch (e.g. `main`).
3. Set **Build Type → Dockerfile**:
   - **Dockerfile Path**: `Dockerfile`
   - **Docker Context Path**: `.`
   - **Docker Build Stage**: leave empty
4. Deploy once to build the image.

### 3. Set environment variables

Application → **Environment**:

```env
DATABASE_URL=postgres://user:password@metascholar-db:5432/metascholar
OPENAI_API_KEY=sk-...
APP_USERNAME=admin
APP_PASSWORD=change-me
AUTO_INIT=true
```

Leave `POSTGRES_HOST` unset so `DATABASE_URL` is used (setting it overrides
`DATABASE_URL`). `AUTO_INIT=true` bootstraps the corpus on first boot (step 6).

### 4. Add a persistent volume for the corpus

Application → **Advanced → Volumes → Add Volume**, mount path **`/app/data`**.

The corpus (`data/corpus.jsonl`) is downloaded at runtime, not baked into the
image, so this volume keeps it across redeploys.

### 5. Add a domain

Application → **Domains → Add Domain**:

- **Host**: `metascholar.example.com`
- **Path**: `/` (root deployment) — leave `ROOT_PATH` unset.
- **Container Port**: `8501`
- **HTTPS**: on

For a **sub-path** deployment (e.g. `https://example.com/metascholar`): set
**Path** to `/metascholar`, leave **Strip Path** *off*, and add the env var
`ROOT_PATH=/metascholar`. Streamlit emits absolute URLs under its
`baseUrlPath`, so the proxy must not strip the prefix.

### 6. Initialize the corpus and index

**Option A — automatic (recommended).** With `AUTO_INIT=true`, the container
waits for Postgres, fetches ~9,900 PubMed abstracts (`make get_data`), embeds
them into Postgres (`make init`), then starts Streamlit. Follow progress in the
application's **Logs** tab. This runs only once; later restarts detect the
populated `articles` table and skip it.

**Option B — manual.** Leave `AUTO_INIT=false` and run once from
Application → **Advanced → Run Command**:

```bash
make get_data && make init
```

`make init` is idempotent, so it is safe to re-run.

### 7. Updates

Push to the connected branch (or hit **Redeploy**). The `/app/data` volume and
the database persist across deployments.

### Notes

- The image builds from the committed `uv.lock`. The entrypoint briefly runs as root to fix the mounted volume's ownership, then drops to the non-root `appuser` (uid `10001`) for the app and bootstrap commands.
- The app listens on `8501` by default; the domain's **Container Port** must match. `PORT` overrides it if needed.
- Healthcheck hits `/_stcore/health` under `ROOT_PATH`.
- `No Postgres configuration found` in the logs means neither `DATABASE_URL` nor the `POSTGRES_*` variables are set on the application.

## Project structure

```
src/metascholar/
├── config.py            # settings (pydantic-settings), env-overridable
├── app/
│   ├── app.py           # Streamlit app: auth, chat, references, feedback
│   ├── dashboard.py     # usage/quality dashboard
│   ├── db_query.py      # conversation + stats queries, pgvector search
│   └── db_feedback.py   # user/judge feedback persistence
├── rag/
│   ├── rag_init.py      # RAG: keyword / vector / hybrid search, prompt, LLM
│   ├── judge.py         # LLM-as-a-judge relevance scoring
│   ├── evaluate.py      # retrieval comparison + prompt A/B
│   └── schemas.py       # LLMCallRecord
├── ingest/
│   └── fetch_data.py    # NCBI E-utilities → corpus.jsonl
└── database/
    └── db_init.py       # schema + corpus embedding/indexing
```

## License

MIT. See [LICENSE](LICENSE).

---

*Built to bridge clinical microbiology domain expertise with LLM application engineering.*
