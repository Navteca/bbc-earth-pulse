"""
DatabasePort — abstract interface for all DB operations.
SQLiteAdapter — default implementation using SQLAlchemy + WAL mode.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import UTC, datetime

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from earth_pulse.models import Article, Enrichment

# --------------------------------------------------------------------------- #
#  Port                                                                        #
# --------------------------------------------------------------------------- #

class DatabasePort(ABC):
    @abstractmethod
    def migrate(self) -> None:
        """Create tables if they do not exist."""
        ...  # pragma: no cover

    @abstractmethod
    def article_exists(self, url_hash: str, title_hash: str) -> bool: ...

    @abstractmethod
    def save_article(self, article: Article) -> None: ...

    @abstractmethod
    def get_unenriched_articles(self, limit: int = 50) -> list[Article]: ...

    @abstractmethod
    def save_enrichment(self, enrichment: Enrichment) -> None: ...

    @abstractmethod
    def mark_enrichment_failed(
        self, article_id: str, reason: str, retry_count: int
    ) -> None: ...

    @abstractmethod
    def get_enriched_articles(
        self,
        region: str | None = None,
        hours: int = 24,
        limit: int = 200,
    ) -> list[tuple[Article, Enrichment]]: ...

    @abstractmethod
    def get_timeline_articles(
        self,
        topic: str,
        since: datetime | None = None,
        limit: int = 200,
    ) -> list[tuple[Article, Enrichment]]: ...


# --------------------------------------------------------------------------- #
#  DDL                                                                         #
# --------------------------------------------------------------------------- #

_DDL = """
CREATE TABLE IF NOT EXISTS articles (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT,
    body_text TEXT,
    url TEXT NOT NULL UNIQUE,
    url_hash TEXT NOT NULL UNIQUE,
    title_hash TEXT NOT NULL,
    source TEXT NOT NULL,
    region TEXT,
    category TEXT,
    language TEXT NOT NULL DEFAULT 'en',
    published_at TEXT NOT NULL,
    ingested_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS enrichments (
    article_id TEXT PRIMARY KEY,
    emotion TEXT,
    topics TEXT,
    narratives TEXT,
    region TEXT,
    urgency_score REAL,
    anxiety_score REAL,
    optimism_score REAL,
    conflict_score REAL,
    stability_score REAL,
    enriched_at TEXT,
    enrichment_failed INTEGER NOT NULL DEFAULT 0,
    failure_reason TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS embeddings (
    article_id TEXT PRIMARY KEY,
    embedding TEXT,
    model TEXT,
    created_at TEXT
);
"""


# --------------------------------------------------------------------------- #
#  SQLite Adapter                                                              #
# --------------------------------------------------------------------------- #

class SQLiteAdapter(DatabasePort):
    """SQLAlchemy + WAL mode SQLite adapter. Swappable with PostgreSQLAdapter in Phase 2."""

    def __init__(self, url: str = "sqlite:///earth_pulse.db") -> None:
        connect_args: dict = {}
        if url.startswith("sqlite"):
            connect_args = {"check_same_thread": False}
            if url == "sqlite:///:memory:":
                self._engine = create_engine(
                    url,
                    connect_args=connect_args,
                    poolclass=StaticPool,
                )
            else:
                self._engine = create_engine(url, connect_args=connect_args)
        else:
            self._engine = create_engine(url)  # pragma: no cover

    def migrate(self) -> None:
        with self._engine.begin() as conn:
            if str(self._engine.url).startswith("sqlite"):
                conn.execute(text("PRAGMA journal_mode=WAL"))
            for statement in _DDL.strip().split(";"):
                stmt = statement.strip()
                if stmt:
                    conn.execute(text(stmt))

    def article_exists(self, url_hash: str, title_hash: str) -> bool:
        with self._engine.connect() as conn:
            row = conn.execute(
                text("SELECT 1 FROM articles WHERE url_hash = :uh LIMIT 1"),
                {"uh": url_hash},
            ).fetchone()
            if row:
                return True
            row = conn.execute(
                text("SELECT 1 FROM articles WHERE title_hash = :th LIMIT 1"),
                {"th": title_hash},
            ).fetchone()
            return row is not None

    def save_article(self, article: Article) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT OR IGNORE INTO articles
                    (id, title, summary, body_text, url, url_hash, title_hash,
                     source, region, category, language, published_at, ingested_at)
                    VALUES
                    (:id, :title, :summary, :body_text, :url, :url_hash, :title_hash,
                     :source, :region, :category, :language, :published_at, :ingested_at)
                    """
                ),
                {
                    "id": article.id,
                    "title": article.title,
                    "summary": article.summary,
                    "body_text": article.body_text,
                    "url": article.url,
                    "url_hash": article.url_hash,
                    "title_hash": article.title_hash,
                    "source": article.source,
                    "region": article.region,
                    "category": article.category,
                    "language": article.language,
                    "published_at": article.published_at.isoformat(),
                    "ingested_at": article.ingested_at.isoformat(),
                },
            )

    def get_unenriched_articles(self, limit: int = 50) -> list[Article]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT a.* FROM articles a
                    LEFT JOIN enrichments e ON a.id = e.article_id
                    WHERE e.article_id IS NULL
                      AND (e.enrichment_failed IS NULL OR e.enrichment_failed = 0)
                    ORDER BY a.ingested_at ASC
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            ).fetchall()
        return [_row_to_article(r) for r in rows]

    def save_enrichment(self, enrichment: Enrichment) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT OR REPLACE INTO enrichments
                    (article_id, emotion, topics, narratives, region,
                     urgency_score, anxiety_score, optimism_score, conflict_score,
                     stability_score, enriched_at, enrichment_failed, failure_reason, retry_count)
                    VALUES
                    (:article_id, :emotion, :topics, :narratives, :region,
                     :urgency_score, :anxiety_score, :optimism_score, :conflict_score,
                     :stability_score, :enriched_at, 0, NULL, :retry_count)
                    """
                ),
                {
                    "article_id": enrichment.article_id,
                    "emotion": enrichment.emotion,
                    "topics": json.dumps(enrichment.topics),
                    "narratives": json.dumps(enrichment.narratives),
                    "region": enrichment.region,
                    "urgency_score": enrichment.urgency_score,
                    "anxiety_score": enrichment.anxiety_score,
                    "optimism_score": enrichment.optimism_score,
                    "conflict_score": enrichment.conflict_score,
                    "stability_score": enrichment.stability_score,
                    "enriched_at": enrichment.enriched_at.isoformat(),
                    "retry_count": enrichment.retry_count,
                },
            )

    def mark_enrichment_failed(
        self, article_id: str, reason: str, retry_count: int
    ) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT OR REPLACE INTO enrichments
                    (article_id, enrichment_failed, failure_reason, retry_count,
                     emotion, topics, narratives, region,
                     urgency_score, anxiety_score, optimism_score, conflict_score,
                     stability_score, enriched_at)
                    VALUES
                    (:article_id, 1, :reason, :retry_count,
                     NULL, '[]', '[]', NULL,
                     0.0, 0.0, 0.0, 0.0, 0.0, :now)
                    """
                ),
                {
                    "article_id": article_id,
                    "reason": reason,
                    "retry_count": retry_count,
                    "now": datetime.now(tz=UTC).isoformat(),
                },
            )

    def get_enriched_articles(
        self,
        region: str | None = None,
        hours: int = 24,
        limit: int = 200,
    ) -> list[tuple[Article, Enrichment]]:
        with self._engine.connect() as conn:
            params: dict = {"hours": hours, "limit": limit}
            region_clause = ""
            if region:
                region_clause = "AND (a.region = :region OR e.region = :region)"
                params["region"] = region
            rows = conn.execute(
                text(
                    f"""
                    SELECT a.*, e.emotion, e.topics, e.narratives, e.region as e_region,
                           e.urgency_score, e.anxiety_score, e.optimism_score,
                           e.conflict_score, e.stability_score, e.enriched_at,
                           e.enrichment_failed, e.failure_reason, e.retry_count
                    FROM articles a
                    JOIN enrichments e ON a.id = e.article_id
                    WHERE e.enrichment_failed = 0
                      AND datetime(a.published_at) >= datetime('now', '-' || :hours || ' hours')
                      {region_clause}
                    ORDER BY e.urgency_score DESC, a.published_at DESC
                    LIMIT :limit
                    """
                ),
                params,
            ).fetchall()
        return [_row_to_article_enrichment(r) for r in rows]

    def get_timeline_articles(
        self,
        topic: str,
        since: datetime | None = None,
        limit: int = 200,
    ) -> list[tuple[Article, Enrichment]]:
        """Return enriched articles matching *topic* as a whole-word search.

        Matching rules (all case-insensitive):
        - ``e.topics`` / ``e.narratives``: JSON arrays — each element is tested
          individually via ``json_each()``.  The topic must appear as a whole
          word within the element (exact, prefix, suffix, or mid-element), so
          ``"AI"`` matches ``"AI governance"`` but not ``"Iran"`` or ``"air
          strikes"``.
        - ``a.title`` / ``a.summary``: plain-text columns — same word-boundary
          pattern applied directly to the column value.
        """
        with self._engine.connect() as conn:
            # Word-boundary fragments reused for every column.
            # Matches: exact | "topic ..." | "... topic" | "... topic ..."
            wb = (
                "lower({col}) = lower(:q)"
                " OR lower({col}) LIKE lower(:q_prefix)"
                " OR lower({col}) LIKE lower(:q_suffix)"
                " OR lower({col}) LIKE lower(:q_mid)"
            )
            params: dict = {
                "q": topic,
                "q_prefix": f"{topic} %",
                "q_suffix": f"% {topic}",
                "q_mid": f"% {topic} %",
                "limit": limit,
            }
            since_clause = ""
            if since:
                since_clause = "AND datetime(a.published_at) >= datetime(:since)"
                params["since"] = since.isoformat()

            # json_each sub-selects: one per JSON-array column.
            topics_match = wb.format(col="jt.value")
            narratives_match = wb.format(col="jn.value")
            title_match = wb.format(col="a.title")
            summary_match = wb.format(col="a.summary")

            rows = conn.execute(
                text(
                    f"""
                    SELECT DISTINCT a.*, e.emotion, e.topics, e.narratives,
                           e.region as e_region,
                           e.urgency_score, e.anxiety_score, e.optimism_score,
                           e.conflict_score, e.stability_score, e.enriched_at,
                           e.enrichment_failed, e.failure_reason, e.retry_count
                    FROM articles a
                    JOIN enrichments e ON a.id = e.article_id
                    LEFT JOIN json_each(e.topics)     AS jt ON ({topics_match})
                    LEFT JOIN json_each(e.narratives) AS jn ON ({narratives_match})
                    WHERE e.enrichment_failed = 0
                      AND (
                            jt.value IS NOT NULL
                            OR jn.value IS NOT NULL
                            OR {title_match}
                            OR {summary_match}
                          )
                      {since_clause}
                    ORDER BY a.published_at ASC
                    LIMIT :limit
                    """
                ),
                params,
            ).fetchall()
        return [_row_to_article_enrichment(r) for r in rows]


# --------------------------------------------------------------------------- #
#  Row mappers                                                                 #
# --------------------------------------------------------------------------- #

def _row_to_article(r: object) -> Article:
    return Article(
        id=r[0],
        title=r[1],
        summary=r[2],
        body_text=r[3],
        url=r[4],
        url_hash=r[5],
        title_hash=r[6],
        source=r[7],
        region=r[8],
        category=r[9],
        language=r[10],
        published_at=datetime.fromisoformat(r[11]),
        ingested_at=datetime.fromisoformat(r[12]),
    )


def _row_to_article_enrichment(r: object) -> tuple[Article, Enrichment]:
    article = Article(
        id=r[0],
        title=r[1],
        summary=r[2],
        body_text=r[3],
        url=r[4],
        url_hash=r[5],
        title_hash=r[6],
        source=r[7],
        region=r[8],
        category=r[9],
        language=r[10],
        published_at=datetime.fromisoformat(r[11]),
        ingested_at=datetime.fromisoformat(r[12]),
    )
    enrichment = Enrichment(
        article_id=r[0],
        emotion=r[13] or "",
        topics=json.loads(r[14] or "[]"),
        narratives=json.loads(r[15] or "[]"),
        region=r[16],
        urgency_score=float(r[17] or 0.0),
        anxiety_score=float(r[18] or 0.0),
        optimism_score=float(r[19] or 0.0),
        conflict_score=float(r[20] or 0.0),
        stability_score=float(r[21] or 0.0),
        enriched_at=datetime.fromisoformat(r[22]) if r[22] else datetime.now(tz=UTC),
        enrichment_failed=bool(r[23]),
        failure_reason=r[24],
        retry_count=int(r[25] or 0),
    )
    return article, enrichment
