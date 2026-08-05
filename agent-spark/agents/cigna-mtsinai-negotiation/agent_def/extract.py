"""
LLM-driven extraction: turn raw page text into structured facts tied to a
HCPCS code / drug name and a leverage dimension, so scoring.py can score them.

Direct port of leverage-agent/agent/extract.py onto the shared entity/fact
schema (agent_spark_core.state uses `entity` where the original schema used
`code`).
"""

import logging

from agent_def import config

log = logging.getLogger("cigna_mtsinai.extract")

MAX_CHARS = 12000  # ~ fits comfortably in LLM_CTX with prompt overhead

EXTRACTION_SYSTEM_PROMPT = """You are a healthcare payer-provider contract analyst working for Cigna. \
You read source documents (CMS regulations, hospital financial filings, price transparency files, \
news, bond disclosures) and extract concrete, sourced facts relevant to Cigna's negotiating leverage \
against Mount Sinai Health System, organized by HCPCS/CPT code or drug name.

For each fact you extract, identify:
- entity: the HCPCS/CPT code or drug name (brand or generic) it pertains to -- e.g. "J9271", "CPT 33945", \
or "Dupilumab". This must be an actual code or drug/procedure name, NEVER one of the dimension labels \
below and NEVER a generic word like "regulatory_pricing" or "market_network". If the fact is general \
(applies broadly, not to a specific code or drug), use exactly "GENERAL".
- dimension: exactly one of "market_network", "financial", "regulatory_pricing", "clinical_uniqueness", \
or null if it doesn't map cleanly to one. This field -- and only this field -- is where those labels belong.
- fact: a single, concrete, self-contained sentence stating the fact (include numbers/dates when present). \
Do not editorialize or score it -- just state the fact.

Only extract facts that are actually useful for assessing negotiating leverage (financial condition, \
market position, regulatory pricing benchmarks, service uniqueness, utilization volume, network adequacy, \
patient volume, payer mix, debt/margins, etc). Ignore boilerplate, navigation text, and irrelevant content.

Respond ONLY with JSON of the form:
{"facts": [{"entity": "...", "dimension": "...", "fact": "..."}, ...]}

If the document has nothing relevant, respond {"facts": []}.
"""

# entity values that are actually dimension labels or other placeholder junk the
# model occasionally emits instead of a real code/drug name -- reject facts with these.
_INVALID_ENTITY_VALUES = {d.lower() for d in config.LEVERAGE_DIMENSIONS} | {
    "none", "null", "n/a", "na", "unknown", "code", "entity", "dimension", "general fact",
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
        if dimension not in config.LEVERAGE_DIMENSIONS:
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
