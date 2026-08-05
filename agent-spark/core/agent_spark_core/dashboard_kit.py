"""
Reusable Streamlit building blocks shared by every agent's dashboard.py.

The pattern: a concrete agent's dashboard.py resolves the agent's single
shared AgentConfig, builds a Store bound to it, and calls into these helpers
for the boilerplate (control-panel sidebar, stats row, flags tab, log tab)
while supplying its own domain-specific tabs (leaderboard, entity drill-down,
etc). Every customer entitled to the agent sees this same dashboard, same
data, same Start/Stop control -- there is no per-customer view (see
instance.py's module docstring).

This keeps every agent's dashboard.py under ~60 lines and guarantees the
Start/Stop/health/log UX is identical across agents, which is the point of
"one reusable pattern" rather than N copy-pasted dashboards.
"""

from __future__ import annotations

import time

import streamlit as st

from agent_spark_core import healthcheck, procmgr
from agent_spark_core.instance import AgentConfig
from agent_spark_core.state import Store


def fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def fmt_ts(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def render_control_sidebar(
    cfg: AgentConfig,
    run_loop_module: str,
    cwd: str,
    *,
    title: str,
    extra_caption_lines: list[str] | None = None,
) -> bool:
    """Renders the Start/Stop control panel + auto-refresh toggle. Returns
    whether auto-refresh is enabled.

    This instance -- and therefore this Start/Stop control -- is shared by
    every customer entitled to the agent: stopping it stops it for everyone,
    starting it starts it for everyone.
    """
    with st.sidebar:
        st.title(title)
        st.caption("Shared instance — visible to every customer entitled to this agent.")

        running, pid = procmgr.is_running(cfg)

        if running:
            uptime = procmgr.uptime_seconds(cfg)
            st.success(f"**Running** (PID {pid})")
            if uptime:
                st.caption(f"Uptime: {fmt_duration(uptime)}")
            if st.button("⏹ Stop agent", type="primary", use_container_width=True):
                with st.spinner("Stopping (waiting for current page to finish)..."):
                    ok, msg = procmgr.stop(cfg)
                st.toast(msg, icon="✅" if ok else "⚠️")
                st.rerun()
        else:
            st.error("**Stopped**")
            if st.button("▶️ Start agent", type="primary", use_container_width=True):
                ok, msg = procmgr.start(run_loop_module, cwd, cfg)
                st.toast(msg, icon="✅" if ok else "⚠️")
                time.sleep(1)
                st.rerun()

        st.divider()
        if not cfg.wiki_repo_url:
            st.caption("⚠️ No wiki_repo_url configured — writing local files only, not synced to GitHub.")
        else:
            st.caption(f"Wiki repo: `{cfg.wiki_repo_url}`")
        for line in extra_caption_lines or []:
            st.caption(line)

        st.divider()
        return st.checkbox("Auto-refresh (10s)", value=True)


def render_stats_row(store: Store, extra_metrics: dict[str, int] | None = None):
    stats = store.stats()
    metrics = {
        "Pages fetched": stats["done"],
        "Pages pending": stats["pending"],
        "Pages failed": stats["failed"],
        "Entities tracked": stats["entities"],
        "Facts extracted": stats["facts"],
        **(extra_metrics or {}),
    }
    cols = st.columns(len(metrics))
    for col, (label, value) in zip(cols, metrics.items()):
        col.metric(label, value)


def render_flags_tab(cfg: AgentConfig):
    flags = healthcheck.recent_flags(cfg, limit=100)
    if not flags:
        st.success("No issues flagged by the health check.")
        return
    st.warning(f"{len(flags)} flag(s) recorded — most recent first.")
    icon_by_kind = {
        "errors_in_log": "💥",
        "stalled": "⏸️",
        "high_failure_rate": "🌐",
        "no_facts_extracted": "🤷",
        "suspect_entity_value": "🏷️",
    }
    for flag in flags:
        kind = flag.get("kind", "unknown")
        icon = icon_by_kind.get(kind, "🚩")
        with st.expander(f"{icon} [{kind}] {fmt_ts(flag['ts'])} — {flag['message'][:100]}"):
            st.write(flag["message"])
            if flag.get("detail"):
                st.json(flag["detail"])

    if st.button("Clear all flags"):
        cfg.review_flags_file.unlink(missing_ok=True)
        st.rerun()


def render_log_tab(cfg: AgentConfig):
    n_lines = st.slider("Lines to show", 50, 1000, 200, step=50)
    st.code(procmgr.tail_log(cfg, n_lines), language="log")


def maybe_autorefresh(enabled: bool, interval_s: int = 10):
    if enabled:
        time.sleep(interval_s)
        st.rerun()
