"""
Trend scoring: given all facts accumulated for a named cost driver, ask the
LLM to score each dimension -- direction, magnitude, confidence, time_horizon
-- with a rationale citing the facts used. Re-scored whenever new facts land
for an entity.

Structurally mirrors cigna-mtsinai-negotiation/agent_def/scoring.py.
"""

import logging

from agent_def import config

log = logging.getLogger("cigna_actuarial.scoring")

SCORING_SYSTEM_PROMPT = f"""You are a healthcare actuarial analyst working for Cigna, assessing how a \
named medical cost trend driver should inform Cigna's medical cost trend assumption.

You will be given a list of facts gathered from CMS regulatory sources, drug pricing/PBM sources, \
hospital cost & utilization data, employer/payer trend reports, and healthcare trade press. Score the \
driver on each of these dimensions:

- direction: Is this driver pushing medical costs up (inflationary, positive score) or down \
(deflationary, e.g. a biosimilar entry or a rate cut, negative score)?
- magnitude: How material is this driver's likely impact on the overall trend assumption -- negligible \
(0) vs. large enough to move the number meaningfully (5)? Score magnitude on its own materiality scale, \
independent of direction (magnitude is always given as a positive-leaning intensity; use 0..5, where the \
sign is carried by the `direction` dimension instead).
- confidence: How well-corroborated is this? A single weak/rumored source is low (0); multiple strong, \
consistent, recent sources is high (5).
- time_horizon: Is this already realized / affecting the current or next plan year (negative score, \
near-term) or is it a longer-term / more speculative signal (positive score, further out or less certain \
to materialize on schedule)?

Score each dimension from {config.SCORE_MIN} to {config.SCORE_MAX} per the definitions above (magnitude \
and confidence are conventionally reported 0..{config.SCORE_MAX} since they represent intensity, not a \
two-sided scale, but stay within the same numeric bounds). 0 means neutral or insufficient evidence. Only \
score a dimension if you have at least one relevant fact -- otherwise omit it.

Respond ONLY with JSON:
{{"scores": [{{"dimension": "...", "score": <number>, "rationale": "<1-3 sentences citing the facts>"}}]}}
"""


def score_entity(llm, store, entity: str) -> list[dict]:
    facts = store.facts_for_entity(entity)
    if not facts:
        return []

    facts_text = "\n".join(f"- [{f['pool']}/{f['dimension'] or 'general'}] {f['fact']}" for f in facts)

    messages = [
        {"role": "system", "content": SCORING_SYSTEM_PROMPT},
        {"role": "user", "content": f"Trend driver: {entity}\n\nFacts gathered so far:\n{facts_text}"},
    ]

    try:
        result = llm.chat_json(messages)
    except Exception as e:
        log.warning("scoring failed for %s: %s", entity, e)
        return []

    scores = result.get("scores", [])
    if not isinstance(scores, list):
        return []

    out = []
    for s in scores:
        if not isinstance(s, dict):
            continue
        dim = s.get("dimension")
        if dim not in config.TREND_DIMENSIONS:
            continue
        try:
            score = float(s.get("score", 0))
        except (TypeError, ValueError):
            continue
        score = max(config.SCORE_MIN, min(config.SCORE_MAX, score))
        rationale = str(s.get("rationale", "")).strip()
        store.upsert_score(entity, dim, score, rationale)
        out.append({"dimension": dim, "score": score, "rationale": rationale})

    return out
