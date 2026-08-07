"""
LLM-driven extraction: turn raw page text into structured facts tied to a
named medical-cost trend driver, so scoring.py can score them.

Structurally mirrors cigna-mtsinai-negotiation/agent_def/extract.py, but the
tracked "entity" here is a trend driver/topic (e.g. "GLP-1 drug spend", "CMS
2026 physician fee schedule conversion factor") rather than a HCPCS code or
drug name -- pages rarely revolve around one code, but reliably revolve
around one cost theme.
"""

import logging

from agent_def import config

log = logging.getLogger("cigna_actuarial.extract")

MAX_CHARS = 12000  # ~ fits comfortably in LLM_CTX with prompt overhead

EXTRACTION_SYSTEM_PROMPT = """You are a healthcare actuarial analyst working for Cigna. You read source \
documents (CMS regulations, drug pricing/PBM reporting, hospital cost & utilization data, employer/payer \
trend reports, healthcare trade press) and extract concrete, sourced facts relevant to Cigna's medical \
cost trend assumptions, organized by named trend driver.

For each fact you extract, identify:
- entity: a short, stable, human-readable name for the trend driver the fact pertains to -- e.g. \
"GLP-1 drug spend", "CMS 2026 physician fee schedule conversion factor", "Specialty pharmacy inflation", \
"Hospital site-of-service shift", "340B program changes". Reuse the same name consistently across facts \
about the same driver (prefer names you have already seen over inventing near-duplicates). This must be \
an actual named cost driver/topic, NEVER one of the dimension labels below and NEVER a generic word like \
"direction" or "magnitude". If the fact is general (applies broadly, not to a specific driver), use \
exactly "GENERAL".
- dimension: exactly one of "direction", "magnitude", "confidence", "time_horizon", or null if it doesn't \
map cleanly to one. This field -- and only this field -- is where those labels belong. In practice most \
extracted facts should leave this null; dimension is primarily set by scoring.py, not extraction -- only \
set it here if the source text itself explicitly frames the fact in those terms.
- fact: a single, concrete, self-contained sentence stating the fact (include numbers/dates/percentages \
when present). Do not editorialize or score it -- just state the fact.

Only extract facts that are actually useful for assessing medical cost trend (unit cost changes, \
utilization changes, drug list price or rebate changes, new FDA approvals with material spend potential, \
regulatory reimbursement changes, site-of-service shifts, published trend/inflation estimates, patent \
cliffs, biosimilar entry, state benefit mandates, etc). Ignore boilerplate, navigation text, and \
irrelevant content.

Respond ONLY with JSON of the form:
{"facts": [{"entity": "...", "dimension": "...", "fact": "..."}, ...]}

If the document has nothing relevant, respond {"facts": []}.
"""

# entity values that are actually dimension labels or other placeholder junk the
# model occasionally emits instead of a real trend-driver name -- reject facts with these.
_INVALID_ENTITY_VALUES = {d.lower() for d in config.TREND_DIMENSIONS} | {
    "none", "null", "n/a", "na", "unknown", "code", "entity", "dimension", "general fact", "trend", "driver",
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
        entity = str(f.get("entity", f.get("code", "GENERAL"))).strip() or "GENERAL"
        dimension = f.get("dimension")
        if dimension not in config.TREND_DIMENSIONS:
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
