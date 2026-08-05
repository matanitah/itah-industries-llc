"""
Per-agent (not per-customer) configuration resolution.

Every agent-spark agent runs exactly **one** shared instance: one background
process, one SQLite DB, one wiki working tree pushing to one GitHub repo, all
under `agents/<slug>/`. Every customer entitled to that agent (see the portal's
`customer_agents` DynamoDB table) sees and controls the *same* instance -- the
same running/stopped state, the same wiki, the same facts. This mirrors the
original leverage-agent's single-process model; the only things layered on
top are (a) N agents can run side by side, and (b) the portal gates who's
allowed to open/start/stop a given agent's dashboard at all.

Configuration lives in `agent.yaml` in the agent's own directory (not
committed if it contains anything sensitive -- only the repo URL lives here,
no credentials; the GitHub PAT used to push is a single Spark-box-wide
secret, see wiki_git.py):

    # agents/cigna-mtsinai-negotiation/agent.yaml
    wiki_repo_url: git@github.com:itah-industries-wikis/wiki-cigna-mtsinai-negotiation.git
    port: 8601
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class AgentConfig:
    """Fully-resolved filesystem/network layout for one agent's single shared instance."""

    agent_slug: str
    agent_root: Path          # .../agents/<agent-slug>
    wiki_dir: Path
    state_db: Path
    log_file: Path
    stdout_log: Path
    pid_file: Path
    raw_cache_dir: Path
    review_flags_file: Path
    wiki_repo_url: str | None
    port: int | None


def _agent_file(agent_root: Path) -> Path:
    return agent_root / "agent.yaml"


def resolve(agent_slug: str, agent_root: Path) -> AgentConfig:
    """Resolve paths/config for one agent's shared instance.

    `agent_root` is the directory containing the agent's own `agent.yaml`
    (i.e. `agents/<agent_slug>/`), passed in by the agent's own config module
    so this stays agent-agnostic.
    """
    declared: dict = {}
    path = _agent_file(agent_root)
    if path.exists():
        declared = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    env_key = agent_slug.upper().replace("-", "_")

    return AgentConfig(
        agent_slug=agent_slug,
        agent_root=agent_root,
        wiki_dir=agent_root / "wiki",
        state_db=agent_root / "logs" / "state.sqlite3",
        log_file=agent_root / "logs" / "agent.log",
        stdout_log=agent_root / "logs" / "stdout.log",
        pid_file=agent_root / "logs" / "agent.pid",
        raw_cache_dir=agent_root / "logs" / "raw_cache",
        review_flags_file=agent_root / "logs" / "review_flags.jsonl",
        wiki_repo_url=declared.get("wiki_repo_url") or os.environ.get(f"AGENT_SPARK_WIKI_REPO_{env_key}"),
        port=declared.get("port") or _int_env(f"AGENT_SPARK_PORT_{env_key}"),
    )


def _int_env(name: str) -> int | None:
    val = os.environ.get(name)
    return int(val) if val and val.isdigit() else None


def ensure_dirs(cfg: AgentConfig) -> None:
    cfg.agent_root.mkdir(parents=True, exist_ok=True)
    cfg.wiki_dir.mkdir(parents=True, exist_ok=True)
    cfg.state_db.parent.mkdir(parents=True, exist_ok=True)
    cfg.raw_cache_dir.mkdir(parents=True, exist_ok=True)
