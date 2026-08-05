"""
Leverage scoring: given all facts accumulated for an entity (HCPCS code or
drug), ask the LLM to score each dimension on a -5 (favors Cigna) .. +5
(favors Mt Sinai) scale, with a rationale citing the facts used. Re-scored
whenever new facts land for an entity.

Direct port of leverage-agent/agent/leverage.py.
"""

import logging

from agent_def import config

log = logging.getLogger("cigna_mtsinai.scoring")

SCORING_SYSTEM_PROMPT = f"""You are a healthcare payer-provider contract analyst working for Cigna, \
assessing negotiating leverage against Mount Sinai Health System for a specific HCPCS/CPT code or drug.

You will be given a list of facts gathered from CMS regulatory sources, Mount Sinai financial/market \
sources, and news. Score negotiating leverage on each of these dimensions:

- market_network: Does Mount Sinai's local market position / network adequacy requirements force Cigna \
to include them (favors Mt Sinai, positive score) or can Cigna credibly exclude/steer around them \
(favors Cigna, negative score)?
- financial: Does Mount Sinai's financial condition (margins, cash reserves, debt covenants, payer mix \
dependency) suggest they need Cigna's patient volume badly (favors Cigna) or can they walk away from a \
bad deal (favors Mt Sinai)?
- regulatory_pricing: Do CMS benchmark rates, price transparency data, or site-of-service rules give \
Cigna a strong reference point to push rates down (favors Cigna) or does regulation constrain Cigna \
more (favors Mt Sinai)?
- clinical_uniqueness: Is this a tertiary/specialty service where Mount Sinai is a must-have provider in \
the market (favors Mt Sinai) or a commodity service available at many competing in-network providers \
(favors Cigna)?

Score each dimension from {config.SCORE_MIN} (strongly favors Cigna) to {config.SCORE_MAX} (strongly \
favors Mount Sinai), with 0 meaning neutral or insufficient evidence. Only score a dimension if you have \
at least one relevant fact -- otherwise omit it.

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
        {"role": "user", "content": f"Entity: {entity}\n\nFacts gathered so far:\n{facts_text}"},
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
        if dim not in config.LEVERAGE_DIMENSIONS:
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
