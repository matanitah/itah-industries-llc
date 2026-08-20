# cigna-actuarial-agent

A long-running local agent that crawls the internet for information related
to medical cost trend drivers -- drug pricing and PBM/rebate dynamics,
hospital facility cost and utilization trend, and CMS regulatory/reimbursement
changes -- and maintains a wiki of relevant insights and how they should
inform Cigna's medical cost trend assumptions. An actuary's primary aim here
is to keep the trend assumption grounded in current evidence; this agent
gathers and organizes that evidence.

Built on the shared [`agent-spark-core`](../../core/README.md) pattern — see
that README for the shared-instance model (one instance, shared by every
customer entitled to this agent, GitHub-backed wiki) and how to add further
agents. This agent is independent of its sibling
[`cigna-mtsinai-negotiation`](../cigna-mtsinai-negotiation/README.md) — own
state DB, own wiki repo, own port — even though both are Cigna-flavored and
share the same underlying framework.

## What it does

Each cycle, rotating across three seed pools:

- **`pharmacy`** — drug pricing (ASP files, WAC/list price moves), specialty
  pharmacy and PBM/rebate trade press, drug shortages, new FDA approvals with
  material spend potential, biosimilar entry / patent cliffs.
- **`medical`** — hospital/facility cost and utilization data, price
  transparency files, and published employer/payer medical cost trend reports
  (Milliman, PwC, Segal, KFF) — these are pre-digested, high-signal sources.
- **`regulatory`** — CMS fee schedules, prospective payment systems, price
  transparency rules, and state benefit mandates (NAIC).

it fetches new frontier pages, extracts sourced facts tied to a named trend
driver (e.g. "GLP-1 drug spend", "CMS 2026 physician fee schedule conversion
factor") via a local LLM (ollama), re-scores every touched driver on four
dimensions (`direction` -5..+5 deflationary↔inflationary, `magnitude` 0..5
materiality, `confidence` 0..5 evidence strength, `time_horizon` -5..+5
near-term↔long-term), and rebuilds the wiki from state. The wiki index ranks
drivers by an expected trend impact composite (`direction` scaled by
`magnitude`) so the most consequential inflationary/deflationary signals
surface first.

## Running locally

```bash
cd agent-spark/agents/cigna-actuarial-agent
cp agent.example.yaml agent.yaml   # fill in the real wiki_repo_url
uv run streamlit run dashboard.py
```

The dashboard's Start/Stop buttons control the one shared background crawl
loop for this agent — there is a single instance, shared by every customer
entitled to it (see [`agent-spark-core`](../../core/README.md)).

## Portal integration

Customers entitled to this agent (via the portal's `customer_agents`
DynamoDB table) all see and control this same dashboard, reverse-proxied
through `spark-gateway` and embedded at `/app/agents/cigna-actuarial-agent`
— see
[`../../../spark/src/spark_gateway/routes/agents.py`](../../../spark/src/spark_gateway/routes/agents.py).
