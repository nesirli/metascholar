# MetaScholar

> RAG-based question answering over the metagenomics & microbiome literature. Ask a question, get an answer grounded in PubMed abstracts, with citations.

![Python](https://img.shields.io/badge/python-3.12%2B-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)
![Postgres](https://img.shields.io/badge/PostgreSQL%20%2B%20pgvector-336791?logo=postgresql&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)

## 🔗 Live demo

**https://portfolio.nasirnesirli.com/metascholar**

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
| Deployment | Docker + Railway |

## Getting started

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Docker (for Postgres + pgvector)
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
docker compose up -d postgres
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

Deployed on [Railway](https://railway.app) as a Docker service connected to a managed PostgreSQL database at **https://metascholar.up.railway.app**.

### Deploying to Railway

1. **Create a Railway project** and add a **PostgreSQL** service.
2. **Add a service** from your GitHub repo (`nesirli/metascholar`). Railway detects the `Dockerfile` automatically.
3. **Connect the database** to the app service so Railway injects `DATABASE_URL` into the app environment.
4. **Set required environment variables** in the app service:
   - `OPENAI_API_KEY`
   - `APP_USERNAME` (default `admin`)
   - `APP_PASSWORD` (default `password`)
5. **Deploy** the app service. The container starts Streamlit on the port provided by Railway's `PORT` variable.
6. **Initialize the database once.** The corpus is gitignored and built at deploy time. Open a shell **via the Railway dashboard** for the running app service (this ensures `DATABASE_URL` and other env vars are present) and run:
   ```bash
   make get_data
   make init
   ```
   Or use the Railway CLI from the linked service:
   ```bash
   railway run make get_data
   railway run make init
   ```
   `make init` creates the schema, enables the `pgvector` extension, and embeds the corpus into Postgres (~9,900 OpenAI calls; idempotent and cheap).

   If you see `No Postgres configuration found`, the shell/command does not have the Railway environment variables. Use the Railway dashboard shell or `railway run` instead of `docker exec`.

### Notes

- The app reads `DATABASE_URL` when available and falls back to individual `POSTGRES_*` variables for local development.
- `ROOT_PATH` is optional. Leave it unset for a root-domain deployment like `metascholar.up.railway.app`; set it only if you run Streamlit behind a reverse proxy under a subpath.
- Railway's `PORT` variable takes precedence over the local default `8501`.

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
