"""
Persistent state for the crawl frontier, visited pages, and extracted facts.

SQLite so an agent instance can be killed/restarted at any point (hours-long
run) and pick back up without re-fetching everything or losing extracted
knowledge. Schema is domain-agnostic: "entity" is whatever the concrete agent
tracks (an HCPCS code/drug for cigna-mtsinai-negotiation, a facility/company/
case for animal-rights-watch); "pool" is whichever of the agent's seed pools
discovered the page (e.g. mt_sinai/cms, or violations/case_law).

Each (agent, customer) instance gets its own DB file (see instance.py) -- this
module just operates on whatever `db_path` it's given, so it's safe to import
from multiple instances/processes without any shared global state.
"""

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS frontier (
    url TEXT PRIMARY KEY,
    pool TEXT NOT NULL,
    depth INTEGER NOT NULL,
    score REAL NOT NULL DEFAULT 1.0,
    discovered_at REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'  -- pending | done | failed | skipped
);

CREATE TABLE IF NOT EXISTS visited (
    url TEXT PRIMARY KEY,
    pool TEXT NOT NULL,
    fetched_at REAL NOT NULL,
    status_code INTEGER,
    content_hash TEXT,
    title TEXT
);

CREATE TABLE IF NOT EXISTS domain_counts (
    domain TEXT PRIMARY KEY,
    count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity TEXT NOT NULL,           -- the tracked thing: code, drug, facility, case, or 'GENERAL'
    pool TEXT NOT NULL,
    dimension TEXT,                 -- one of the agent's scoring dimensions, or NULL for raw facts
    fact TEXT NOT NULL,
    source_url TEXT NOT NULL,
    extracted_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS scores (
    entity TEXT NOT NULL,
    dimension TEXT NOT NULL,
    score REAL NOT NULL,
    rationale TEXT,
    updated_at REAL NOT NULL,
    PRIMARY KEY (entity, dimension)
);

CREATE INDEX IF NOT EXISTS idx_facts_entity ON facts(entity);
CREATE INDEX IF NOT EXISTS idx_frontier_status ON frontier(status, pool);
"""


class Store:
    """Thin, connection-per-call SQLite wrapper bound to one instance's DB file."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def db(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self):
        with self.db() as conn:
            conn.executescript(SCHEMA)

    # --- frontier -----------------------------------------------------------

    def seed_frontier(self, seeds: list[tuple[str, str]]):
        """seeds: list of (url, pool)"""
        with self.db() as conn:
            for url, pool in seeds:
                conn.execute(
                    "INSERT OR IGNORE INTO frontier (url, pool, depth, score, discovered_at, status) "
                    "VALUES (?, ?, 0, 5.0, ?, 'pending')",
                    (url, pool, time.time()),
                )

    def enqueue(self, url: str, pool: str, depth: int, score: float):
        with self.db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO frontier (url, pool, depth, score, discovered_at, status) "
                "VALUES (?, ?, ?, ?, ?, 'pending')",
                (url, pool, depth, score, time.time()),
            )

    def next_batch(self, pool: str, limit: int) -> list[sqlite3.Row]:
        with self.db() as conn:
            cur = conn.execute(
                "SELECT * FROM frontier WHERE pool = ? AND status = 'pending' "
                "ORDER BY score DESC, depth ASC LIMIT ?",
                (pool, limit),
            )
            return cur.fetchall()

    def mark_status(self, url: str, status: str):
        with self.db() as conn:
            conn.execute("UPDATE frontier SET status = ? WHERE url = ?", (status, url))

    def record_visit(self, url: str, pool: str, status_code: int, content_hash: str, title: str):
        with self.db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO visited (url, pool, fetched_at, status_code, content_hash, title) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (url, pool, time.time(), status_code, content_hash, title),
            )

    def is_visited(self, url: str) -> bool:
        with self.db() as conn:
            cur = conn.execute("SELECT 1 FROM visited WHERE url = ?", (url,))
            return cur.fetchone() is not None

    def domain_count(self, domain: str) -> int:
        with self.db() as conn:
            cur = conn.execute("SELECT count FROM domain_counts WHERE domain = ?", (domain,))
            row = cur.fetchone()
            return row["count"] if row else 0

    def increment_domain_count(self, domain: str):
        with self.db() as conn:
            conn.execute(
                "INSERT INTO domain_counts (domain, count) VALUES (?, 1) "
                "ON CONFLICT(domain) DO UPDATE SET count = count + 1",
                (domain,),
            )

    # --- facts / scores -------------------------------------------------------

    def add_fact(self, entity: str, pool: str, dimension: str | None, fact: str, source_url: str):
        with self.db() as conn:
            conn.execute(
                "INSERT INTO facts (entity, pool, dimension, fact, source_url, extracted_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (entity, pool, dimension, fact, source_url, time.time()),
            )

    def facts_for_entity(self, entity: str) -> list[sqlite3.Row]:
        with self.db() as conn:
            cur = conn.execute("SELECT * FROM facts WHERE entity = ? ORDER BY extracted_at", (entity,))
            return cur.fetchall()

    def all_entities(self) -> list[str]:
        with self.db() as conn:
            cur = conn.execute("SELECT DISTINCT entity FROM facts WHERE entity != 'GENERAL' ORDER BY entity")
            return [r["entity"] for r in cur.fetchall()]

    def upsert_score(self, entity: str, dimension: str, score: float, rationale: str):
        with self.db() as conn:
            conn.execute(
                "INSERT INTO scores (entity, dimension, score, rationale, updated_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(entity, dimension) DO UPDATE SET score=excluded.score, "
                "rationale=excluded.rationale, updated_at=excluded.updated_at",
                (entity, dimension, score, rationale, time.time()),
            )

    def scores_for_entity(self, entity: str) -> list[sqlite3.Row]:
        with self.db() as conn:
            cur = conn.execute("SELECT * FROM scores WHERE entity = ?", (entity,))
            return cur.fetchall()

    def stats(self) -> dict:
        with self.db() as conn:
            pending = conn.execute("SELECT COUNT(*) c FROM frontier WHERE status='pending'").fetchone()["c"]
            done = conn.execute("SELECT COUNT(*) c FROM frontier WHERE status='done'").fetchone()["c"]
            failed = conn.execute("SELECT COUNT(*) c FROM frontier WHERE status='failed'").fetchone()["c"]
            entities = conn.execute(
                "SELECT COUNT(DISTINCT entity) c FROM facts WHERE entity != 'GENERAL'"
            ).fetchone()["c"]
            facts = conn.execute("SELECT COUNT(*) c FROM facts").fetchone()["c"]
            return {"pending": pending, "done": done, "failed": failed, "entities": entities, "facts": facts}
