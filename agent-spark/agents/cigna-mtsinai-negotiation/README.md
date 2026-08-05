# cigna-mtsinai-negotiation

A long-running local agent that crawls the internet for information related
to Mt Sinai (particularly their financials) and CMS regulatory/reimbursement
data, and maintains a wiki of relevant information and how it applies to
Cigna's provider-contract negotiation strategy with Mt Sinai. An insurance
company's primary aim in this negotiation is to negotiate effectively and
keep prices low; this agent gathers and organizes the evidence for that.

Built on the shared [`agent-spark-core`](../../core/README.md) pattern — see
that README for the shared-instance model (one instance, shared by every
customer entitled to this agent, GitHub-backed wiki) and how to add further
agents.

## What it does

Each cycle, alternating between two seed pools:

- **`mt_sinai`** — financial statements, nonprofit filings (ProPublica/
  GuideStar), municipal bond disclosures (Mt Sinai issues tax-exempt bonds),
  price-transparency files, NY state hospital utilization data, and
  healthcare trade press.
- **`cms`** — Medicare fee schedules, prospective payment systems, price
  transparency rules, No Surprises Act guidance, and HCPCS coding references.

it fetches new frontier pages, extracts sourced facts tied to a specific
HCPCS/CPT code or drug name via a local LLM (ollama), re-scores every touched
code on four leverage dimensions (`market_network`, `financial`,
`regulatory_pricing`, `clinical_uniqueness`, each -5..+5 where negative favors
Cigna and positive favors Mt Sinai), and rebuilds the wiki from state.

## Running locally

```bash
cd agent-spark/agents/cigna-mtsinai-negotiation
cp agent.example.yaml agent.yaml   # fill in the real wiki_repo_url
uv run streamlit run dashboard.py
```

The dashboard's Start/Stop buttons control the one shared background crawl
loop for this agent — there is a single instance, shared by every customer
entitled to it (see [`agent-spark-core`](../../core/README.md)).

## Portal integration

Customers entitled to this agent (via the portal's `customer_agents`
DynamoDB table) all see and control this same dashboard, reverse-proxied
through `spark-gateway` and embedded at `/app/agents/cigna-mtsinai-negotiation`
— see
[`../../../spark/src/spark_gateway/routes/agents.py`](../../../spark/src/spark_gateway/routes/agents.py).
