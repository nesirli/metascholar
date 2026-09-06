"""Database query functions for conversations, stats, and feedback."""

import psycopg
from dataclasses import dataclass
from openai import OpenAI

from metascholar.config import settings
from metascholar.rag.schemas import LLMCallRecord

_embed_client = None


def _get_embed_client():
    global _embed_client
    if _embed_client is None:
        _embed_client = OpenAI(api_key=settings.openai_api_key)
    return _embed_client


def embed_text(text: str, model: str = "text-embedding-3-small") -> list[float]:
    """Generate an embedding vector for a text string."""
    resp = _get_embed_client().embeddings.create(model=model, input=text)
    return resp.data[0].embedding


def pg_vector_search(query: str, top_k: int = 5) -> list[dict]:
    """Search articles by vector similarity using pgvector cosine distance."""
    emb = embed_text(query)
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT pmid, title, abstract, year, journal,
               1 - (embedding <=> %s::vector) AS similarity
               FROM articles ORDER BY embedding <=> %s::vector LIMIT %s""",
            (emb, emb, top_k),
        ).fetchall()
        return [
            {"pmid": r[0], "title": r[1], "abstract": r[2],
             "year": r[3], "journal": r[4], "similarity": float(r[5])}
            for r in rows
        ]
    finally:
        conn.close()


def _get_conn():
    """Create a new database connection using settings from config."""
    return psycopg.connect(**settings.get_postgres_kwargs())


@dataclass
class ConversationRecord:
    """A flattened row from the llm_calls table for dashboard display."""
    question: str
    prompt: str
    answer: str
    model: str
    response_time: float
    cost: float
    timestamp: str


@dataclass
class Stats:
    """Aggregate stats across all llm_calls."""
    total: int
    avg_response_time: float
    total_cost: float
    avg_tokens: float


def save_llm_call(record: LLMCallRecord) -> int:
    """Persist an LLMCallRecord to llm_calls and its sources to llm_call_sources.
    Returns the new call_id."""
    conn = _get_conn()
    try:
        row = conn.execute(
            """INSERT INTO llm_calls (question, answer, model, instructions, prompt,
               prompt_tokens, completion_tokens, total_tokens, response_time, cost, timestamp)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (record.question, record.answer, record.model, record.instructions,
             record.prompt, record.prompt_tokens, record.completion_tokens,
             record.total_tokens, record.response_time, record.cost, record.timestamp),
        ).fetchone()
        call_id = row[0]
        for rank, src in enumerate(record.sources, 1):
            conn.execute(
                "INSERT INTO llm_call_sources (call_id, pmid, rank) VALUES (%s, %s, %s)",
                (call_id, src["pmid"], rank),
            )
        conn.commit()
        return call_id
    finally:
        conn.close()


def get_conversations(limit: int = 100) -> list[ConversationRecord]:
    """Fetch recent conversations ordered by timestamp descending."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT question, prompt, answer, model, response_time, cost, timestamp::text "
            "FROM llm_calls ORDER BY timestamp DESC LIMIT %s",
            (limit,),
        ).fetchall()
        return [ConversationRecord(*r) for r in rows]
    finally:
        conn.close()


def get_stats() -> Stats:
    """Return aggregate usage stats from the llm_calls table."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT count(*), coalesce(avg(response_time), 0), "
            "coalesce(sum(cost), 0), coalesce(avg(total_tokens), 0) "
            "FROM llm_calls"
        ).fetchone()
        return Stats(*row)
    finally:
        conn.close()


def get_relevance_stats() -> dict[str, int]:
    """Count feedback rows grouped by relevance verdict (judge evaluations)."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT coalesce(relevance, 'UNKNOWN'), count(*) "
            "FROM feedback WHERE source = 'judge' GROUP BY relevance"
        ).fetchall()
        return {r[0]: r[1] for r in rows}
    finally:
        conn.close()


def get_user_feedback_stats() -> tuple[int, int]:
    """Return counts of positive (score=1) and negative (score=-1) user feedback."""
    conn = _get_conn()
    try:
        up, down = conn.execute(
            "SELECT coalesce(sum(case when score = 1 then 1 else 0 end), 0), "
            "coalesce(sum(case when score = -1 then 1 else 0 end), 0) "
            "FROM feedback WHERE source = 'user'"
        ).fetchone()
        return up, down
    finally:
        conn.close()
