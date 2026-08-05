"""
agent_spark_core — the reusable "agent-spark" pattern shared by every
long-running crawl agent + Streamlit dashboard in agent-spark/agents/*.

Extracted from the original leverage-agent (Cigna <-> Mt Sinai) prototype.
A concrete agent implements only the domain-specific pieces:

  - config.py     seeds, crawl policy (keywords/domain weights), scoring dimensions
  - extract.py    LLM prompt turning page text -> [{"entity", "dimension", "fact"}]
  - scoring.py    LLM prompt turning accumulated facts -> per-dimension scores
  - wiki.py       markdown rendering of entities + index
  - run_loop.py   wires the above into agent_spark_core.loop.main(...)
  - dashboard.py  wires agent_spark_core.dashboard_kit into agent-specific tabs

...and gets, for free: multi-tenant instance isolation (per-customer PID/DB/
wiki), politeness-respecting crawling, GitHub-backed wiki sync, health
monitoring, and a consistent Start/Stop Streamlit control panel.
"""
