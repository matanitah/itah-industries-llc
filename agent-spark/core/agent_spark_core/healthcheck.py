"""
Periodic self-check: scans recent activity for signs of trouble (errors,
silent extraction anomalies, stalled progress, data-quality issues like a
dimension-name-as-entity bug) and records flags for later human review.

This does NOT try to auto-fix anything -- it only detects and records, so a
human can review the agent's review_flags.jsonl (or the dashboard)
periodically without having to babysit the raw log in real time.

Domain-specific "suspect entity value" checks are supplied by the concrete
agent (its scoring dimension names + a few generic placeholders), everything
else is generic across agents.
"""

import json
import logging
import time

from agent_spark_core.instance import AgentConfig
from agent_spark_core.state import Store

log = logging.getLogger("agent_spark_core.healthcheck")

_GENERIC_SUSPECT_VALUES = {"none", "null", "n/a", "na", "unknown", "code", "entity", "dimension", "general fact"}


def _flag(cfg: AgentConfig, kind: str, message: str, detail: dict | None = None):
    entry = {"ts": time.time(), "kind": kind, "message": message, "detail": detail or {}}
    cfg.review_flags_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cfg.review_flags_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    log.warning("REVIEW FLAG [%s]: %s", kind, message)


def _check_suspect_entities(cfg: AgentConfig, store: Store, dimension_names: list[str]):
    suspect_values = {d.lower() for d in dimension_names} | _GENERIC_SUSPECT_VALUES
    with store.db() as conn:
        rows = conn.execute("SELECT DISTINCT entity FROM facts WHERE entity != 'GENERAL'").fetchall()
    hits = [r["entity"] for r in rows if r["entity"].strip().lower() in suspect_values]
    if hits:
        _flag(
            cfg,
            "suspect_entity_value",
            f"{len(hits)} entity value(s) in the facts table look like dimension labels or placeholders, "
            f"not real tracked entities: {hits}. Likely an extraction prompt regression.",
            {"entities": hits},
        )


def _check_failure_rate(cfg: AgentConfig, store: Store, window_s: float = 3600):
    cutoff = time.time() - window_s
    with store.db() as conn:
        failed = conn.execute(
            "SELECT COUNT(*) c FROM visited WHERE fetched_at >= ? AND (status_code IS NULL OR status_code >= 400)",
            (cutoff,),
        ).fetchone()["c"]
        recent = conn.execute("SELECT COUNT(*) c FROM visited WHERE fetched_at >= ?", (cutoff,)).fetchone()["c"]

    if recent >= 10 and failed / recent > 0.5:
        _flag(
            cfg,
            "high_failure_rate",
            f"{failed}/{recent} pages fetched in the last hour failed (status>=400 or fetch error). "
            f"Possible blocking, robots.txt issue, or dead source.",
            {"failed": failed, "recent": recent},
        )


def _check_stalled_progress(cfg: AgentConfig, store: Store, window_s: float = 3600):
    cutoff = time.time() - window_s
    with store.db() as conn:
        recent_visits = conn.execute("SELECT COUNT(*) c FROM visited WHERE fetched_at >= ?", (cutoff,)).fetchone()["c"]
        recent_facts = conn.execute("SELECT COUNT(*) c FROM facts WHERE extracted_at >= ?", (cutoff,)).fetchone()["c"]
    pending = store.stats()["pending"]

    if pending > 0 and recent_visits == 0:
        _flag(
            cfg,
            "stalled",
            "No pages were fetched in the last hour despite a non-empty frontier. "
            "The loop may be stuck, crashed silently, or blocked on a slow request.",
            {"pending": pending},
        )
    elif recent_visits >= 20 and recent_facts == 0:
        _flag(
            cfg,
            "no_facts_extracted",
            f"{recent_visits} pages were fetched in the last hour but zero facts were extracted. "
            f"Extraction may be silently failing (LLM errors, JSON parse failures, or thin/irrelevant pages).",
            {"recent_visits": recent_visits},
        )


def _check_error_log_tail(cfg: AgentConfig, window_s: float = 3600):
    if not cfg.log_file.exists():
        return
    error_lines = []
    try:
        with open(cfg.log_file, encoding="utf-8", errors="ignore") as f:
            for line in f:
                if " ERROR " in line or " CRITICAL " in line or "Traceback" in line:
                    error_lines.append(line.rstrip())
    except OSError:
        return

    if error_lines:
        recent_errors = error_lines[-20:]
        _flag(
            cfg,
            "errors_in_log",
            f"{len(error_lines)} error/traceback line(s) found in agent.log (showing up to last 20).",
            {"lines": recent_errors},
        )


def run_healthcheck(cfg: AgentConfig, store: Store, dimension_names: list[str]) -> int:
    """Run all checks. Safe to call repeatedly; each check appends flags independently."""
    log.info("running health check for %s", cfg.agent_slug)
    checks = [
        lambda: _check_suspect_entities(cfg, store, dimension_names),
        lambda: _check_failure_rate(cfg, store),
        lambda: _check_stalled_progress(cfg, store),
        lambda: _check_error_log_tail(cfg),
    ]
    flagged_before = _count_flags(cfg)
    for check in checks:
        try:
            check()
        except Exception:
            log.exception("healthcheck subcheck itself failed")
            _flag(cfg, "healthcheck_error", "a health check subcheck raised an exception")
    new_flags = _count_flags(cfg) - flagged_before
    log.info("health check complete (%d new flag(s))", new_flags)
    return new_flags


def _count_flags(cfg: AgentConfig) -> int:
    if not cfg.review_flags_file.exists():
        return 0
    with open(cfg.review_flags_file, encoding="utf-8") as f:
        return sum(1 for _ in f)


def recent_flags(cfg: AgentConfig, limit: int = 50) -> list[dict]:
    if not cfg.review_flags_file.exists():
        return []
    lines = cfg.review_flags_file.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(out))
