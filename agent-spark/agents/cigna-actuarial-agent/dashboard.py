"""
Streamlit control panel for the Cigna actuarial medical-cost-trend agent.

Run via: uv run streamlit run dashboard.py
(or ./start-dev.sh cigna-actuarial-agent from the repo root)

Lets you start/stop the background crawl loop, watch live crawl stats,
browse the trend-impact leaderboard, drill into a driver's supporting facts,
and review flags raised by the health check. There is exactly one shared
instance of this agent -- every customer entitled to it sees this same
dashboard and data (see agent_spark_core/instance.py).
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from agent_spark_core import dashboard_kit, healthcheck
from agent_spark_core import instance as instance_mod
from agent_spark_core.state import Store

from agent_def import config

AGENT_SLUG = "cigna-actuarial-agent"
AGENT_ROOT = Path(__file__).resolve().parent
RUN_LOOP_MODULE = "agent_def.run_loop"

st.set_page_config(page_title="Cigna Actuarial Trend Agent", page_icon="📈", layout="wide")

cfg = instance_mod.resolve(AGENT_SLUG, AGENT_ROOT)
store = Store(cfg.state_db)

auto_refresh = dashboard_kit.render_control_sidebar(
    cfg,
    RUN_LOOP_MODULE,
    str(AGENT_ROOT),
    title="📈 Agent Control",
    extra_caption_lines=[
        f"Model: `{config.MODEL}` via ollama",
        f"Cycle sleep: {config.CYCLE_SLEEP_S}s · batch: {config.MAX_PAGES_PER_CYCLE}/pool",
    ],
)

st.title("Cigna Medical Cost Trend Agent")
dashboard_kit.render_stats_row(store)
st.divider()


def _impact_score(scores: dict) -> float | None:
    direction = scores.get("direction")
    magnitude = scores.get("magnitude")
    if not direction or not magnitude:
        return None
    d = direction["score"]
    m = magnitude["score"]
    sign = 1 if d >= 0 else -1
    return sign * (abs(d) * m / config.SCORE_MAX)


tab_report, tab_drivers, tab_flags, tab_log = st.tabs(
    ["📊 Trend Report", "🔍 Driver Detail", "🚩 Review Flags", "📜 Live Log"]
)

with tab_report:
    with store.db() as conn:
        rows = conn.execute("SELECT entity, dimension, score, rationale FROM scores").fetchall()

    if not rows:
        st.info("No drivers scored yet. Once the agent has crawled enough pages, scored trend drivers will appear here.")
    else:
        by_entity = {}
        for r in rows:
            by_entity.setdefault(r["entity"], {})[r["dimension"]] = r

        table_rows = []
        for entity, scores in by_entity.items():
            impact = _impact_score(scores)
            confidence = scores.get("confidence", {}).get("score")
            table_rows.append(
                {
                    "Driver": entity,
                    "Trend Impact": round(impact, 1) if impact is not None else None,
                    "Confidence": round(confidence, 1) if confidence is not None else None,
                    "Dimensions Scored": f"{len(scores)}/4",
                    "Leans": "Inflationary" if (impact or 0) > 0.5 else ("Deflationary" if (impact or 0) < -0.5 else "Neutral"),
                }
            )

        df = pd.DataFrame(table_rows).sort_values("Trend Impact", ascending=False, na_position="last")

        col_chart, col_table = st.columns([1, 1.3])
        with col_chart:
            st.caption("Expected trend impact by driver (negative = deflationary, positive = inflationary)")
            chart_df = df.dropna(subset=["Trend Impact"]).set_index("Driver")[["Trend Impact"]]
            st.bar_chart(chart_df, height=max(300, 24 * len(df)))
        with col_table:
            st.dataframe(df, use_container_width=True, hide_index=True, height=max(300, 35 * len(df)))

    st.divider()
    index_path = cfg.wiki_dir / "index.md"
    st.caption(f"Wiki index: `{index_path}` — regenerated every cycle.")
    if index_path.exists():
        with st.expander("View raw wiki/index.md"):
            st.markdown(index_path.read_text(encoding="utf-8"))

with tab_drivers:
    entities = store.all_entities()
    if not entities:
        st.info("No trend drivers tracked yet.")
    else:
        selected = st.selectbox("Select a trend driver", sorted(entities))
        if selected:
            scores = store.scores_for_entity(selected)
            facts = store.facts_for_entity(selected)

            if scores:
                cols = st.columns(len(scores))
                for col, s in zip(cols, scores):
                    col.metric(s["dimension"].replace("_", " ").title(), f"{s['score']:+.1f}")
                for s in scores:
                    with st.expander(f"{s['dimension'].replace('_', ' ').title()} rationale"):
                        st.write(s["rationale"] or "_no rationale recorded_")
            else:
                st.warning("Not yet scored.")

            st.subheader(f"Supporting facts ({len(facts)})")
            for f in facts:
                dim = f["dimension"].replace("_", " ").title() if f["dimension"] else "unclassified"
                st.markdown(
                    f"- **[{dim}]** {f['fact']}  \n  <sub>source: {f['source_url']}</sub>",
                    unsafe_allow_html=True,
                )

with tab_flags:
    dashboard_kit.render_flags_tab(cfg)

with tab_log:
    dashboard_kit.render_log_tab(cfg)

dashboard_kit.maybe_autorefresh(auto_refresh)
