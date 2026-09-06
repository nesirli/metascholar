import psycopg
import json
from pathlib import Path
from datetime import datetime
from openai import OpenAI
from tqdm import tqdm

from metascholar.config import settings

DB_TIMEZONE = datetime.now().astimezone().tzinfo
print(f"Using timezone: {DB_TIMEZONE}")

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def embed(text: str, model: str = "text-embedding-3-small") -> list[float]:
    resp = _get_client().embeddings.create(model=model, input=text)
    return resp.data[0].embedding


def get_db_connection():
    return psycopg.connect(**settings.get_postgres_kwargs())


def init_db():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute("""
                         CREATE TABLE IF NOT EXISTS articles
                         (
                             pmid TEXT PRIMARY KEY,
                             title TEXT,
                             abstract TEXT,
                             year TEXT,
                             journal TEXT,
                             embedding VECTOR(1536)
                         )
                         """)
            cur.execute("""
                         CREATE INDEX IF NOT EXISTS idx_articles_embedding
                         ON articles USING hnsw (embedding vector_cosine_ops)
                         """)
            cur.execute("""
                        CREATE TABLE IF NOT EXISTS llm_calls
                        (
                            id SERIAL PRIMARY KEY,
                            question TEXT NOT NULL,
                            answer TEXT NOT NULL,
                            model TEXT NOT NULL,
                            instructions TEXT NOT NULL,
                            prompt TEXT NOT NULL,
                            prompt_tokens INTEGER NOT NULL,
                            completion_tokens INTEGER NOT NULL,
                            total_tokens INTEGER NOT NULL,
                            response_time FLOAT NOT NULL,
                            cost FLOAT NOT NULL,
                            timestamp TIMESTAMP WITH TIME ZONE NOT NULL
                        )
                        """)
            cur.execute("""
                        CREATE TABLE IF NOT EXISTS llm_call_sources 
                            (
                            call_id INTEGER REFERENCES llm_calls(id),
                            pmid TEXT REFERENCES articles(pmid),
                            rank INTEGER NOT NULL,
                            PRIMARY KEY (call_id, pmid)
                            )
                        """)
            cur.execute("""
                         CREATE TABLE IF NOT EXISTS feedback
                         (
                            id SERIAL PRIMARY KEY,
                            llm_call_id INTEGER REFERENCES llm_calls(id),
                            source TEXT NOT NULL,
                            relevance TEXT,
                            explanation TEXT,
                            score INTEGER,
                            timestamp TIMESTAMP WITH TIME ZONE NOT NULL
                         )
                        """)
        conn.commit()
    finally:
        conn.close()


def index_corpus(conn: psycopg.Connection, corpus_path: Path):
    lines = corpus_path.read_text(encoding="utf-8").strip().splitlines()
    for line in tqdm(lines, desc="Indexing", unit="article"):
        r = json.loads(line)
        emb = embed(r["abstract"])
        conn.execute(
            """INSERT INTO articles (pmid, title, abstract, year, journal, embedding)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (pmid) DO NOTHING""",
            (r["pmid"], r["title"], r["abstract"], r["year"], r["journal"], emb),
        )
    conn.commit()


if __name__ == "__main__":
    init_db()
    index_corpus(get_db_connection(), settings.corpus_path)
    print("Database initialized and corpus indexed.")
