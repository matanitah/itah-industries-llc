"""
LLM-driven extraction: turn raw page text into structured facts tied to a
tracked entity (a company/facility/operator for the `violations` pool, or a
named case for the `case_law` pool), so scoring.py can score them.

Modeled directly on cigna-mtsinai-negotiation's extract.py, swapped to this
agent's domain and entity conventions.
"""

import logging

from agent_def import config

log = logging.getLogger("animal_rights_watch.extract")

MAX_CHARS = 12000

EXTRACTION_SYSTEM_PROMPT = """You are a researcher for an animal-rights watchdog organization. You read \
source documents (USDA/APHIS enforcement records, investigative reporting from animal-welfare \
organizations, court opinions, state legislative material, and news) and extract concrete, sourced facts \
about (a) systemic animal-rights violations by specific companies, facilities, or operators, and (b) \
animal-cruelty / animal-rights case law across all 50 US states.

For each fact you extract, identify:
- entity: the specific thing this fact is about. For violation facts, this is the company, facility, or \
operator name (e.g. "Smithfield Foods", "Envigo RMS Cumberland Facility"). For case-law facts, this is the \
case name in standard citation-style form (e.g. "People v. Youngblood", "ALDF v. Wasden"). This must be an \
actual named entity or case, NEVER one of the scoring dimension labels below and NEVER a generic word like \
"severity" or "case_law". If the fact is general (applies broadly, not to one specific entity or case), use \
exactly "GENERAL".
- dimension: exactly one of "evidence_strength", "severity", "legal_exposure", "recency", or null if the \
fact doesn't map cleanly to scoring (e.g. pure background/context). This field -- and only this field -- is \
where those labels belong.
- fact: a single, concrete, self-contained sentence stating the fact (include numbers, dates, locations, \
and state names when present). Do not editorialize or score it -- just state the fact.

Only extract facts that are actually useful for assessing (1) how well-documented and severe a systemic \
animal-rights violation is, or (2) the substance and outcome of animal-rights case law. Ignore boilerplate, \
navigation text, opinion/advocacy rhetoric without factual content, and irrelevant material.

Respond ONLY with JSON of the form:
{"facts": [{"entity": "...", "dimension": "...", "fact": "..."}, ...]}

If the document has nothing relevant, respond {"facts": []}.
"""

_INVALID_ENTITY_VALUES = {d.lower() for d in config.SCORING_DIMENSIONS} | {
    "none", "null", "n/a", "na", "unknown", "entity", "dimension", "general fact",
    "violations", "case_law", "violation", "case law",
}


def extract_facts(llm, text: str, source_url: str, pool: str) -> list[dict]:
    if not text or len(text.strip()) < 200:
        return []

    chunk = text[:MAX_CHARS]

    messages = [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Source URL: {source_url}\nSource pool: {pool}\n\nDocument text:\n{chunk}",
        },
    ]

    try:
        result = llm.chat_json(messages)
    except Exception as e:
        log.warning("extraction failed for %s: %s", source_url, e)
        return []

    facts = result.get("facts", [])
    if not isinstance(facts, list):
        return []

    cleaned = []
    dropped = 0
    for f in facts:
        if not isinstance(f, dict):
            continue
        entity = str(f.get("entity", "GENERAL")).strip() or "GENERAL"
        dimension = f.get("dimension")
        if dimension not in config.SCORING_DIMENSIONS:
            dimension = None
        fact_text = str(f.get("fact", "")).strip()
        if not fact_text:
            continue
        if entity.lower() in _INVALID_ENTITY_VALUES:
            dropped += 1
            entity = "GENERAL"
        cleaned.append({"entity": entity, "dimension": dimension, "fact": fact_text})

    if dropped:
        log.warning("normalized %d fact(s) with invalid entity value to GENERAL", dropped)

    return cleaned
