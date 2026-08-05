"""
Severity/confidence scoring: given all facts accumulated for a tracked entity
(a company/facility/operator, or a case), ask the LLM to score each dimension
on a 0..5 scale, with a rationale citing the facts used. Re-scored whenever
new facts land for an entity.

Unlike cigna-mtsinai-negotiation's bipolar leverage scale, these dimensions
are unipolar: 0 is "weak/none", 5 is "strong/severe/clear" -- there's no
opposing side to favor, just how well-documented and serious the situation is.
"""

import logging

from agent_def import config

log = logging.getLogger("animal_rights_watch.scoring")

SCORING_SYSTEM_PROMPT = f"""You are a researcher for an animal-rights watchdog organization, assessing \
how well-documented and serious a tracked entity's situation is. The entity is either a company/facility/ \
operator (from the `violations` pool) or a specific animal-cruelty/animal-rights court case (from the \
`case_law` pool).

You will be given a list of facts gathered from USDA/APHIS enforcement records, investigative reporting, \
court opinions, and state legislative sources. Score on each of these dimensions (0..5, unipolar -- there \
is no "other side" here, just how strong the evidence/severity/exposure/recency is):

- evidence_strength: 0 = anecdotal or unsubstantiated claims only, 5 = documented by regulatory findings, \
adjudicated court records, or multiple independent corroborating sources.
- severity: 0 = minor or isolated incident, 5 = systemic, mass-scale, or repeated cruelty affecting many \
animals or spanning a long period.
- legal_exposure: 0 = no clear statutory violation identified in the facts, 5 = a clear, specific statutory \
violation is identified, ideally with an active enforcement action, charge, or ruling.
- recency: 0 = old, resolved, or purely historical, 5 = active or ongoing as of the most recent facts \
gathered.

Score {config.SCORE_MIN} (weakest/least) to {config.SCORE_MAX} (strongest/most). Only score a dimension if \
you have at least one relevant fact -- otherwise omit it.

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
        if dim not in config.SCORING_DIMENSIONS:
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
