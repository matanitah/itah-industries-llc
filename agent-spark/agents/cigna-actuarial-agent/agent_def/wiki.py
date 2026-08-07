"""
Markdown wiki writer. One page per named medical-cost trend driver, plus an
auto-generated index sorted by expected trend impact (most inflationary
first) so an actuary can scan for what should move next year's assumption.

Pages are fully regenerated from the store on each write (idempotent), so the
wiki is always a clean projection of the SQLite state -- no drift. Writes land
in the instance's `wiki_dir`, which agent_spark_core.wiki_git then commits and
pushes to the agent's shared GitHub repo.

Structurally mirrors cigna-mtsinai-negotiation/agent_def/wiki.py; "leverage"
becomes "trend impact" and the four dimensions are direction/magnitude/
confidence/time_horizon instead of the negotiation-leverage set.
"""

import time
from datetime import datetime, timezone

from slugify import slugify

from agent_def import config

DIMENSION_LABELS = {
    "direction": "Direction (deflationary ↔ inflationary)",
    "magnitude": "Magnitude (materiality)",
    "confidence": "Confidence (evidence strength)",
    "time_horizon": "Time Horizon (near-term ↔ long-term)",
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _bar(score: float, low_label: str, high_label: str) -> str:
    """Render a simple text bar between two labels, e.g. Deflationary <===|===> Inflationary"""
    pos = round((score - config.SCORE_MIN) / (config.SCORE_MAX - config.SCORE_MIN) * 20)
    pos = max(0, min(20, pos))
    return f"{low_label} " + ("─" * pos) + "●" + ("─" * (20 - pos)) + f" {high_label}"


def _impact_score(scores: dict) -> float | None:
    """Composite 'expected trend impact': direction's sign/scale weighted by
    magnitude's intensity (0..5), normalized back to the -5..+5 range so it's
    comparable to a plain direction score. None if we don't have both."""
    direction = scores.get("direction")
    magnitude = scores.get("magnitude")
    if not direction or not magnitude:
        return None
    d = direction["score"]
    m = magnitude["score"]
    sign = 1 if d >= 0 else -1
    return sign * (abs(d) * m / config.SCORE_MAX)


def write_entity_page(store, cfg, entity: str):
    facts = store.facts_for_entity(entity)
    scores = {s["dimension"]: s for s in store.scores_for_entity(entity)}

    slug = slugify(entity)
    path = cfg.wiki_dir / "drivers" / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = [f"# {entity}", "", f"_Last updated: {_now()}_", ""]

    if scores:
        impact = _impact_score(scores)
        lines += ["## Trend Impact Summary", ""]
        if impact is not None:
            lines.append(
                f"**Expected trend impact: {impact:+.1f}** "
                "(negative = deflationary pressure, positive = inflationary pressure)"
            )
            lines.append("")
        lines.append("| Dimension | Score | |")
        lines.append("|---|---|---|")
        for dim in config.TREND_DIMENSIONS:
            s = scores.get(dim)
            if not s:
                continue
            if dim == "direction":
                bar = _bar(s["score"], "Deflationary", "Inflationary")
            elif dim == "time_horizon":
                bar = _bar(s["score"], "Near-term", "Long-term")
            else:
                bar = _bar(s["score"], "Low", "High")
            lines.append(f"| {DIMENSION_LABELS[dim]} | {s['score']:+.1f} | `{bar}` |")
        lines.append("")

        lines.append("## Rationale by Dimension")
        lines.append("")
        for dim in config.TREND_DIMENSIONS:
            s = scores.get(dim)
            if not s:
                continue
            lines.append(f"### {DIMENSION_LABELS[dim]} ({s['score']:+.1f})")
            lines.append("")
            lines.append(s["rationale"] or "_no rationale recorded_")
            lines.append("")
    else:
        lines += ["## Trend Impact Summary", "", "_Not yet scored -- insufficient facts gathered._", ""]

    lines.append("## Supporting Facts")
    lines.append("")
    if facts:
        for f in facts:
            dim_label = DIMENSION_LABELS.get(f["dimension"], "unclassified") if f["dimension"] else "unclassified"
            lines.append(f"- **[{dim_label}]** {f['fact']}  ")
            lines.append(f"  _source: <{f['source_url']}>_")
    else:
        lines.append("_No facts gathered yet._")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def write_index(store, cfg):
    entities = store.all_entities()
    rows = []
    for entity in entities:
        scores = {s["dimension"]: s for s in store.scores_for_entity(entity)}
        if not scores:
            continue
        impact = _impact_score(scores)
        confidence_row = scores.get("confidence")
        confidence = confidence_row["score"] if confidence_row else None
        rows.append((entity, impact, confidence, len(scores)))

    # Most inflationary first; entities without both direction+magnitude sort last.
    rows.sort(key=lambda r: (r[1] is None, -(r[1] or 0)))

    lines = [
        "# Cigna Medical Cost Trend Wiki",
        "",
        f"_Last updated: {_now()}_",
        "",
        "Auto-generated by the cigna-actuarial-agent. Each page tracks one named medical-cost trend "
        "driver (a drug, a regulatory change, a utilization shift, etc.) across four dimensions: "
        "direction, magnitude, confidence, and time horizon -- the inputs an actuary would fold into "
        "Cigna's medical cost trend assumption.",
        "",
        "Direction/time-horizon scale: **-5 = strongly deflationary / near-term** ... **0 = neutral** "
        "... **+5 = strongly inflationary / long-term**. Magnitude/confidence scale: **0 = negligible / "
        "unconfirmed** ... **5 = material / well-corroborated**.",
        "",
        "## Drivers Ranked by Expected Trend Impact (most inflationary first)",
        "",
        "| Driver | Trend Impact | Confidence | Dimensions Scored | Page |",
        "|---|---|---|---|---|",
    ]
    for entity, impact, confidence, n_dims in rows:
        slug = slugify(entity)
        impact_str = f"{impact:+.1f}" if impact is not None else "_n/a_"
        conf_str = f"{confidence:.1f}" if confidence is not None else "_n/a_"
        lines.append(f"| {entity} | {impact_str} | {conf_str} | {n_dims}/4 | [view](drivers/{slug}.md) |")

    if not rows:
        lines.append("| _(none scored yet)_ | | | | |")

    stats = store.stats()
    lines += [
        "",
        "## Crawl Stats",
        "",
        f"- Pages fetched: {stats['done']}",
        f"- Pages pending: {stats['pending']}",
        f"- Pages failed: {stats['failed']}",
        f"- Drivers tracked: {stats['entities']}",
        f"- Facts extracted: {stats['facts']}",
        "",
    ]

    path = cfg.wiki_dir / "index.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def rebuild_all(store, cfg):
    """Regenerate every entity page + index from current DB state."""
    t0 = time.time()
    entities = store.all_entities()
    for entity in entities:
        write_entity_page(store, cfg, entity)
    write_index(store, cfg)
    import logging

    logging.getLogger("cigna_actuarial.wiki").info(
        "wiki rebuilt (%d drivers) in %.1fs", len(entities), time.time() - t0
    )
