# agent-spark

Long-running local agents: each crawls the web on a schedule, extracts
structured facts via a local LLM (ollama), scores/ranks what it finds, and
maintains a markdown wiki of the results — controlled through a Streamlit
dashboard with Start/Stop buttons, and (when entitled) reachable from the
Itah Industries customer portal.

```
agent-spark/
├── core/                          # the reusable pattern — see core/README.md
│   └── agent_spark_core/
├── agents/
│   ├── cigna-mtsinai-negotiation/  # Cigna <-> Mt Sinai contract-leverage research
│   └── animal-rights-watch/        # systemic animal-rights violations + 50-state case law
└── start-dev.sh                    # ./start-dev.sh <agent-slug>
```

## Quick start

```bash
cd agent-spark/agents/<agent-slug>
cp agent.example.yaml agent.yaml   # declare the wiki_repo_url + port for this agent's one shared instance
cd ../..
./start-dev.sh <agent-slug>
```

Open the printed localhost URL, hit **Start agent**, and watch the frontier,
facts, and leaderboard fill in over the next few cycles.

## The pattern

Every agent here is built the same way, factored out of the original
`leverage-agent` prototype into [`agent-spark-core`](core/README.md):

1. **Crawl** an alternating pair of seed pools (politeness-respecting,
   robots.txt-aware, relevance-scored so the frontier doesn't wander
   off-topic).
2. **Extract** structured facts from each page via a local LLM, tied to a
   tracked entity (a code/drug, a company, a legal case, ...).
3. **Score** each touched entity on a small set of domain-specific
   dimensions, with an LLM-written rationale.
4. **Render** a markdown wiki (one page per entity + a ranked index),
   regenerated fresh from SQLite every cycle — never hand-edited, never
   drifts from state.
5. **Sync** the wiki to a GitHub repo dedicated to that agent, under the
   `itah-industries-wikis` org.
6. Repeat, sleep, and run an hourly health check for silent failures.

See [`core/README.md`](core/README.md) for the full shared-vs-agent-specific
breakdown and the shared-instance model: each agent runs exactly **one**
instance, shared by every customer entitled to it — e.g. every customer
entitled to `cigna-mtsinai-negotiation` sees the same crawl progress and
wiki, not a private copy — while `animal-rights-watch` (a different agent)
runs fully independently alongside it, in parallel.

## Portal integration

The customer portal (`../website/`) lists the agents a signed-in customer is
entitled to and embeds their dashboard, reverse-proxied through
`../spark/src/spark_gateway/routes/agents.py`. See that route and
`../ARCHITECTURE.md` §7/§12 for the entitlement + proxy wiring.
