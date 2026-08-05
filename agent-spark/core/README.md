# agent-spark-core

The reusable "agent-spark" pattern: a long-running crawl-and-extract loop plus
a Streamlit control-panel dashboard, factored out of the original
`leverage-agent` (Cigna ↔ Mt Sinai) prototype so every new agent under
`agent-spark/agents/*` gets it for free instead of copy-pasting it.

## What's shared vs. what each agent supplies

| Shared (`agent_spark_core`) | Agent-specific (`agents/<slug>/agent_def/`) |
|---|---|
| Single-shared-instance resolution (`instance.py`) — one PID/DB/wiki per agent, total | `config.py` — seed URLs, keywords, domain weights, scoring dimensions |
| SQLite frontier/facts/scores schema (`state.py`) | `extract.py` — LLM prompt: page text → facts |
| Politeness-respecting crawler + link scoring (`crawler.py`) | `scoring.py` — LLM prompt: facts → per-dimension score + rationale |
| Ollama chat client (`llm.py`) | `wiki.py` — markdown rendering of one entity page + the index |
| GitHub-backed wiki sync (`wiki_git.py`) | `run_loop.py` — thin `agent_spark_core.loop.main(...)` wiring |
| Start/stop process control (`procmgr.py`) | `dashboard.py` — thin `agent_spark_core.dashboard_kit` wiring + domain tabs |
| Hourly health checks (`healthcheck.py`) | |
| Cycle driver (`loop.py`) | |
| Streamlit control-panel building blocks (`dashboard_kit.py`) | |

## Shared state across customers

Every agent runs **exactly one instance, shared by every customer entitled to
it** — one background process, one SQLite DB, one wiki, pushed to one GitHub
repo dedicated to that agent. If customer A and customer B are both entitled
to `cigna-mtsinai-negotiation`, they see the same dashboard, the same crawl
progress, the same wiki, and the same Start/Stop control — starting or
stopping it affects it for everyone. This mirrors how the original
leverage-agent worked (a single process); the portal layers per-customer
**entitlement** (who's allowed to open/start/stop a given agent at all) on
top, in DynamoDB's `customer_agents` table — that's a separate concern from
the shared instance itself.

Configuration is declared per-agent in `agents/<slug>/agent.yaml`:

```yaml
wiki_repo_url: https://github.com/itah-industries-wikis/wiki-cigna-mtsinai-negotiation.git
port: 8601
```

`wiki_repo_url` must be `https://github.com/...` (not `git@github.com:...`) —
see `wiki_git.py`'s docstring for why (fine-grained PATs only authenticate
over HTTPS). One repo is pre-provisioned per **agent** under the
`itah-industries-wikis` GitHub org — not per customer.

## Adding a new agent

1. `agents/<slug>/pyproject.toml` depending on `agent-spark-core` (path dependency) + any extra libs.
2. `agents/<slug>/agent_def/config.py|extract.py|scoring.py|wiki.py` (domain content).
3. `agents/<slug>/agent_def/run_loop.py`:
   ```python
   from pathlib import Path
   from agent_spark_core import loop
   from agent_def.config import build_definition

   if __name__ == "__main__":
       loop.main(agent_slug="<slug>", agent_root=Path(__file__).resolve().parent.parent, build_definition=build_definition)
   ```
4. `agents/<slug>/dashboard.py` using `agent_spark_core.dashboard_kit` (see either existing agent for the ~60-line template).
5. `agents/<slug>/agent.yaml` with that agent's `wiki_repo_url` + `port` (copy `agent.example.yaml`).
