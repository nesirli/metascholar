"""Save feedback (judge evaluations and user ratings) to the database."""

import psycopg

from metascholar.config import settings


def _get_conn():
    """Create a new database connection using settings from config."""
    return psycopg.connect(**settings.get_postgres_kwargs())


def save_feedback(
    conversation_id: int,
    source: str,
    relevance: str | None = None,
    explanation: str | None = None,
    score: int | None = None,
) -> None:
    """Insert a feedback row for a given conversation.

    source='judge'  → relevance + explanation from the LLM judge
    source='user'   → score=1 (helpful) or score=-1 (not helpful)
    """
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT INTO feedback (llm_call_id, source, relevance, explanation, score, timestamp)
               VALUES (%s, %s, %s, %s, %s, NOW())""",
            (conversation_id, source, relevance, explanation, score),
        )
        conn.commit()
    finally:
        conn.close()
