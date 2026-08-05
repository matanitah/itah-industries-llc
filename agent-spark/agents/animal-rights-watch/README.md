# animal-rights-watch

A long-running local agent that crawls the internet for systemic animal-rights
violations — patterns implicating specific companies, facilities, or
operators, sourced from regulatory enforcement records and investigative
reporting — and separately gathers animal-rights/animal-cruelty case law
across all 50 US states. It maintains a wiki ranking tracked entities and
cases by how severe and well-documented the situation is.

Built on the shared [`agent-spark-core`](../../core/README.md) pattern —
same agent-loop and Streamlit dashboard shape as
[`cigna-mtsinai-negotiation`](../cigna-mtsinai-negotiation/README.md), just
pointed at a different domain. See the core README for the shared-instance
model (one instance, shared by every customer entitled to this agent,
GitHub-backed wiki).

## What it does

Each cycle, alternating between two seed pools:

- **`violations`** — USDA/APHIS Animal Welfare Act enforcement actions, Fish
  & Wildlife Service enforcement, EPA factory-farm environmental enforcement,
  and investigative reporting from Animal Equality, Mercy For Animals, the
  Humane Society, ALDF, PETA, and Sentient Media.
- **`case_law`** — ALDF's litigation docket, the Michigan State Animal Legal
  & Historical Center case database (covers all 50 states), CourtListener
  opinion search, NCSL's state animal-cruelty-law tracker, and Justia.

it fetches new frontier pages, extracts sourced facts tied to a specific
company/facility/operator (`violations` pool) or named case (`case_law`
pool) via a local LLM (ollama), re-scores every touched entity on four
0–5 severity/confidence dimensions (`evidence_strength`, `severity`,
`legal_exposure`, `recency` — unipolar, since there's no "other side" to
favor here unlike the leverage-negotiation agent), and rebuilds the wiki
from state, ranked by composite priority (highest = most severe /
well-documented / urgent).

## Running locally

```bash
cd agent-spark/agents/animal-rights-watch
cp agent.example.yaml agent.yaml   # fill in the real wiki_repo_url
uv run streamlit run dashboard.py
```

## Portal integration

Customers entitled to this agent (via the portal's `customer_agents`
DynamoDB table) all see and control this same dashboard, reverse-proxied
through `spark-gateway` and embedded at `/app/agents/animal-rights-watch` —
see
[`../../../spark/src/spark_gateway/routes/agents.py`](../../../spark/src/spark_gateway/routes/agents.py).
