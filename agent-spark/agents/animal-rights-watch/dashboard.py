"""
Streamlit control panel for the animal-rights-watch agent.

Run via: uv run streamlit run dashboard.py
(or ./start-dev.sh animal-rights-watch from the repo root)

Lets you start/stop the background crawl loop, watch live crawl stats,
browse the priority leaderboard (companies/facilities and case law ranked by
how severe/well-documented they are), drill into an entity's supporting
facts, and review flags raised by the health check. There is exactly one
shared instance of this agent -- every customer entitled to it sees this
same dashboard and data (see agent_spark_core/instance.py).
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from agent_spark_core import dashboard_kit
from agent_spark_core import instance as instance_mod
from agent_spark_core.state import Store

from agent_def import config

AGENT_SLUG = "animal-rights-watch"
AGENT_ROOT = Path(__file__).resolve().parent
RUN_LOOP_MODULE = "agent_def.run_loop"

st.set_page_config(page_title="Animal Rights Watch Agent", page_icon="🐾", layout="wide")

cfg = instance_mod.resolve(AGENT_SLUG, AGENT_ROOT)
store = Store(cfg.state_db)

auto_refresh = dashboard_kit.render_control_sidebar(
    cfg,
    RUN_LOOP_MODULE,
    str(AGENT_ROOT),
    title="🐾 Agent Control",
    extra_caption_lines=[
        f"Model: `{config.MODEL}` via ollama",
        f"Cycle sleep: {config.CYCLE_SLEEP_S}s · batch: {config.MAX_PAGES_PER_CYCLE}/pool",
    ],
)

st.title("Animal Rights Watch Agent")
st.caption("Tracking systemic animal-rights violations and 50-state animal-rights case law.")
dashboard_kit.render_stats_row(store)
st.divider()

tab_report, tab_detail, tab_flags, tab_log = st.tabs(
    ["📊 Priority Report", "🔍 Entity / Case Detail", "🚩 Review Flags", "📜 Live Log"]
)

with tab_report:
    with store.db() as conn:
        rows = conn.execute("SELECT entity, dimension, score, rationale FROM scores").fetchall()
        # scores has no pool column (see agent_spark_core/state.py's SCHEMA) --
        # pool is per-fact, so pull each entity's pool from its facts instead.
        pool_rows = conn.execute("SELECT DISTINCT entity, pool FROM facts").fetchall()

    if not rows:
        st.info("No entities scored yet. Once the agent has crawled enough pages, scored entities will appear here.")
    else:
        pool_by_entity = {r["entity"]: r["pool"] for r in pool_rows}
        by_entity = {}
        for r in rows:
            by_entity.setdefault(r["entity"], []).append(r)

        table_rows = []
        for entity, scores in by_entity.items():
            composite = sum(s["score"] for s in scores) / len(scores)
            table_rows.append(
                {
                    "Entity / Case": entity,
                    "Pool": pool_by_entity.get(entity, "unknown"),
                    "Composite Priority": round(composite, 1),
                    "Dimensions Scored": f"{len(scores)}/4",
                }
            )

        df = pd.DataFrame(table_rows).sort_values("Composite Priority", ascending=False)

        col_chart, col_table = st.columns([1, 1.3])
        with col_chart:
            st.caption("Composite priority (0-5, higher = more severe/well-documented/urgent)")
            chart_df = df.set_index("Entity / Case")[["Composite Priority"]]
            st.bar_chart(chart_df, height=max(300, 24 * len(df)))
        with col_table:
            st.dataframe(df, use_container_width=True, hide_index=True, height=max(300, 35 * len(df)))

    st.divider()
    index_path = cfg.wiki_dir / "index.md"
    st.caption(f"Wiki index: `{index_path}` — regenerated every cycle.")
    if index_path.exists():
        with st.expander("View raw wiki/index.md"):
            st.markdown(index_path.read_text(encoding="utf-8"))

with tab_detail:
    entities = store.all_entities()
    if not entities:
        st.info("No entities tracked yet.")
    else:
        selected = st.selectbox("Select a company/facility or case", sorted(entities))
        if selected:
            scores = store.scores_for_entity(selected)
            facts = store.facts_for_entity(selected)

            if scores:
                cols = st.columns(len(scores))
                for col, s in zip(cols, scores):
                    col.metric(s["dimension"].replace("_", " ").title(), f"{s['score']:.1f}/5")
                for s in scores:
                    with st.expander(f"{s['dimension'].replace('_', ' ').title()} rationale"):
                        st.write(s["rationale"] or "_no rationale recorded_")
            else:
                st.warning("Not yet scored.")

            st.subheader(f"Supporting facts ({len(facts)})")
            for f in facts:
                dim = f["dimension"].replace("_", " ").title() if f["dimension"] else "unclassified"
                st.markdown(
                    f"- **[{dim}]** {f['fact']}  \n  <sub>source: {f['source_url']} · pool: {f['pool']}</sub>",
                    unsafe_allow_html=True,
                )

with tab_flags:
    dashboard_kit.render_flags_tab(cfg)

with tab_log:
    dashboard_kit.render_log_tab(cfg)

dashboard_kit.maybe_autorefresh(auto_refresh)
