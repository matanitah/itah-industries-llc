"""
Streamlit control panel for the Cigna <-> Mt Sinai contract-leverage agent.

Run via: uv run streamlit run dashboard.py
(or ./start-dev.sh cigna-mtsinai-negotiation from the repo root)

Lets you start/stop the background crawl loop, watch live crawl stats,
browse the leverage leaderboard, visualize scores from on-disk wiki pages,
drill into a code's supporting facts, and review flags raised by the health
check. There is exactly one shared instance of this agent -- every customer
entitled to it sees this same dashboard and data (see
agent_spark_core/instance.py).
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import streamlit as st

from agent_spark_core import dashboard_kit, healthcheck
from agent_spark_core import instance as instance_mod
from agent_spark_core.state import Store

from agent_def import config

AGENT_SLUG = "cigna-mtsinai-negotiation"
AGENT_ROOT = Path(__file__).resolve().parent
RUN_LOOP_MODULE = "agent_def.run_loop"

# Labels written by agent_def.wiki — used to parse dimension rows back out.
_DIM_LABEL_TO_KEY = {
    "Market / Network Position": "market_network",
    "Financial Condition": "financial",
    "Regulatory & Pricing Benchmarks": "regulatory_pricing",
    "Clinical Uniqueness": "clinical_uniqueness",
}

_NET_LEVERAGE_RE = re.compile(
    r"\*\*Net leverage:\s*([+-]?\d+(?:\.\d+)?)\*\*",
    re.IGNORECASE,
)
_TITLE_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_DIM_ROW_RE = re.compile(
    r"^\|\s*(?P<label>[^|]+?)\s*\|\s*(?P<score>[+-]?\d+(?:\.\d+)?)\s*\|",
    re.MULTILINE,
)


@st.cache_data(ttl=30)
def _load_wiki_code_scores(wiki_dir: str) -> pd.DataFrame:
    """Parse leverage scores from wiki/codes/*.md (projection may include orphans)."""
    codes_dir = Path(wiki_dir) / "codes"
    if not codes_dir.is_dir():
        return pd.DataFrame()

    rows: list[dict] = []
    for path in sorted(codes_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        title_m = _TITLE_RE.search(text)
        entity = title_m.group(1).strip() if title_m else path.stem

        net_m = _NET_LEVERAGE_RE.search(text)
        dims: dict[str, float] = {}
        for m in _DIM_ROW_RE.finditer(text):
            label = m.group("label").strip()
            if label.lower() == "dimension":
                continue
            key = _DIM_LABEL_TO_KEY.get(label)
            if not key:
                continue
            dims[key] = float(m.group("score"))

        if net_m:
            net = float(net_m.group(1))
            scored = True
        elif dims:
            net = sum(dims.values()) / len(dims)
            scored = True
        else:
            net = None
            scored = False

        row = {
            "Code": entity,
            "Slug": path.stem,
            "Net Leverage": round(net, 1) if net is not None else None,
            "Dimensions Scored": f"{len(dims)}/4" if scored else "0/4",
            "n_dims": len(dims),
            "Leans Toward": (
                "Cigna"
                if net is not None and net < -0.5
                else ("Mt Sinai" if net is not None and net > 0.5 else ("Neutral" if scored else "Unscored"))
            ),
            "Scored": scored,
            "Page": str(path),
        }
        for key in config.LEVERAGE_DIMENSIONS:
            row[key] = dims.get(key)
        rows.append(row)

    return pd.DataFrame(rows)


st.set_page_config(page_title="Cigna ↔ Mt Sinai Leverage Agent", page_icon="⚖️", layout="wide")

cfg = instance_mod.resolve(AGENT_SLUG, AGENT_ROOT)
store = Store(cfg.state_db)

auto_refresh = dashboard_kit.render_control_sidebar(
    cfg,
    RUN_LOOP_MODULE,
    str(AGENT_ROOT),
    title="⚖️ Agent Control",
    extra_caption_lines=[
        f"Model: `{config.MODEL}` via ollama",
        f"Cycle sleep: {config.CYCLE_SLEEP_S}s · batch: {config.MAX_PAGES_PER_CYCLE}/pool",
    ],
)

st.title("Cigna ↔ Mt Sinai Contract Leverage Agent")
dashboard_kit.render_stats_row(store)
st.divider()

tab_report, tab_wiki, tab_codes, tab_flags, tab_log = st.tabs(
    ["📊 Leverage Report", "📖 Wiki Scores", "🔍 Code Detail", "🚩 Review Flags", "📜 Live Log"]
)

with tab_report:
    with store.db() as conn:
        rows = conn.execute("SELECT entity, dimension, score, rationale FROM scores").fetchall()

    if not rows:
        st.info("No codes scored yet. Once the agent has crawled enough pages, scored codes will appear here.")
    else:
        by_entity = {}
        for r in rows:
            by_entity.setdefault(r["entity"], []).append(r)

        table_rows = []
        for entity, scores in by_entity.items():
            net = sum(s["score"] for s in scores) / len(scores)
            table_rows.append(
                {
                    "Code": entity,
                    "Net Leverage": round(net, 1),
                    "Dimensions Scored": f"{len(scores)}/4",
                    "Leans Toward": "Cigna" if net < -0.5 else ("Mt Sinai" if net > 0.5 else "Neutral"),
                }
            )

        df = pd.DataFrame(table_rows).sort_values("Net Leverage")

        col_chart, col_table = st.columns([1, 1.3])
        with col_chart:
            st.caption("Net leverage by code (negative = favors Cigna, positive = favors Mt Sinai)")
            chart_df = df.set_index("Code")[["Net Leverage"]]
            st.bar_chart(chart_df, height=max(300, 24 * len(df)))
        with col_table:
            st.dataframe(df, use_container_width=True, hide_index=True, height=max(300, 35 * len(df)))

    st.divider()
    index_path = cfg.wiki_dir / "index.md"
    st.caption(f"Wiki index: `{index_path}` — regenerated every cycle.")
    if index_path.exists():
        with st.expander("View raw wiki/index.md"):
            st.markdown(index_path.read_text(encoding="utf-8"))

with tab_wiki:
    st.caption(
        "Scores parsed from on-disk `wiki/codes/*.md` — includes pages still present after "
        "older crawls even if they are no longer in the live SQLite state."
    )
    wiki_df = _load_wiki_code_scores(str(cfg.wiki_dir))
    if wiki_df.empty:
        st.info("No wiki code pages found under `wiki/codes/`.")
    else:
        scored_df = wiki_df[wiki_df["Scored"]].copy()
        live_entities = set(store.all_entities())
        wiki_df = wiki_df.assign(InLiveDB=wiki_df["Code"].isin(live_entities))

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Wiki pages", len(wiki_df))
        m2.metric("Scored in wiki", int(wiki_df["Scored"].sum()))
        m3.metric("Unscored pages", int((~wiki_df["Scored"]).sum()))
        m4.metric("Also in live DB", int(wiki_df["InLiveDB"].sum()))

        if scored_df.empty:
            st.warning("Wiki pages exist, but none contain leverage scores yet.")
        else:
            scored_df = scored_df.sort_values("Net Leverage")

            st.subheader("Net leverage distribution")
            hist = (
                scored_df.assign(bucket=scored_df["Net Leverage"].round(0).astype(int))
                .groupby("bucket", as_index=False)
                .size()
                .rename(columns={"bucket": "Net Leverage", "size": "Codes"})
                .set_index("Net Leverage")
            )
            st.bar_chart(hist, height=220)
            st.caption("Codes per rounded net-leverage score (negative = favors Cigna, positive = favors Mt Sinai)")

            top_n = st.slider("Codes per extreme chart", min_value=10, max_value=50, value=25, step=5)
            col_cigna, col_mts = st.columns(2)
            with col_cigna:
                st.caption(f"Most Cigna-favorable (bottom {top_n})")
                cigna_df = scored_df.head(top_n).set_index("Code")[["Net Leverage"]]
                st.bar_chart(cigna_df, height=max(280, 18 * len(cigna_df)))
            with col_mts:
                st.caption(f"Most Mt Sinai-favorable (top {top_n})")
                mts_df = scored_df.tail(top_n).iloc[::-1].set_index("Code")[["Net Leverage"]]
                st.bar_chart(mts_df, height=max(280, 18 * len(mts_df)))

            st.subheader("Dimension averages (scored wiki pages)")
            dim_avgs = {
                dim.replace("_", " ").title(): round(scored_df[dim].dropna().mean(), 2)
                for dim in config.LEVERAGE_DIMENSIONS
                if scored_df[dim].notna().any()
            }
            if dim_avgs:
                st.bar_chart(pd.Series(dim_avgs, name="Avg score"), height=220)

            st.subheader("All wiki codes")
            show = st.radio(
                "Filter",
                ["Scored only", "All pages", "Unscored only", "Not in live DB"],
                horizontal=True,
                label_visibility="collapsed",
            )
            view = wiki_df
            if show == "Scored only":
                view = wiki_df[wiki_df["Scored"]]
            elif show == "Unscored only":
                view = wiki_df[~wiki_df["Scored"]]
            elif show == "Not in live DB":
                view = wiki_df[~wiki_df["InLiveDB"]]

            query = st.text_input("Filter by code name", placeholder="e.g. aflibercept, 71101, vivitrol")
            if query.strip():
                view = view[view["Code"].str.contains(query.strip(), case=False, na=False)]

            display_cols = [
                "Code",
                "Net Leverage",
                "Dimensions Scored",
                "Leans Toward",
                "InLiveDB",
                *config.LEVERAGE_DIMENSIONS,
            ]
            table = view[display_cols].sort_values(
                "Net Leverage", ascending=True, na_position="last"
            )
            st.dataframe(table, use_container_width=True, hide_index=True, height=420)

            pick_options = sorted(scored_df["Code"].tolist())
            if pick_options:
                selected = st.selectbox("Inspect a scored wiki code", pick_options)
                detail = scored_df[scored_df["Code"] == selected].iloc[0]
                dim_cols = st.columns(4)
                for col, dim in zip(dim_cols, config.LEVERAGE_DIMENSIONS):
                    val = detail[dim]
                    col.metric(
                        dim.replace("_", " ").title(),
                        f"{val:+.1f}" if pd.notna(val) else "—",
                    )
                page_path = Path(detail["Page"])
                if page_path.exists():
                    with st.expander(f"Raw wiki page · `{page_path.name}`"):
                        st.markdown(page_path.read_text(encoding="utf-8", errors="replace"))

with tab_codes:
    entities = store.all_entities()
    if not entities:
        st.info("No codes tracked yet.")
    else:
        selected = st.selectbox("Select a code / drug", sorted(entities))
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
