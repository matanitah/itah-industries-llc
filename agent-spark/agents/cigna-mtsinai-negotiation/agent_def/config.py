"""
Domain configuration for the Cigna <-> Mt Sinai contract-leverage agent.

Two seed pools feed one crawl frontier:
  - MT_SINAI_SEEDS: financial / market / clinical-uniqueness signal for the provider side
  - CMS_SEEDS: regulatory / reimbursement-benchmark signal for the payer side

Crawling is "open-ended" in the sense that discovered links are followed, but
every discovered domain is scored for relevance before being queued (see
agent_spark_core.crawler), and off-topic domains decay out of the frontier
quickly.

This module is the direct port of the original `leverage-agent/agent/config.py`
content onto the shared `agent_spark_core` pattern -- the seeds, keywords, and
scoring dimensions are unchanged; only the plumbing (paths, per-instance
state) now comes from `agent_spark_core.instance`.
"""

from agent_spark_core.crawler import CrawlPolicy

# ---------------------------------------------------------------------------
# LLM (local, via ollama)
# ---------------------------------------------------------------------------
OLLAMA_HOST = "http://127.0.0.1:11434"
MODEL = "gpt-oss:20b"
LLM_TIMEOUT_S = 300
LLM_CTX = 8192  # keep prompts within this; chunk long documents

# ---------------------------------------------------------------------------
# Seed sources
# ---------------------------------------------------------------------------
MT_SINAI_SEEDS = [
    # Financial disclosures
    "https://www.mountsinai.org/about/financial-statements",
    "https://projects.propublica.org/nonprofits/organizations/131624096",  # Mount Sinai Hospital ProPublica Nonprofit Explorer
    "https://www.guidestar.org/profile/13-1624096",
    "https://emma.msrb.org/",  # Municipal bond disclosures (Mt Sinai issues tax-exempt bonds)
    # Price transparency (federal machine-readable file requirement)
    "https://www.mountsinai.org/about/price-transparency",
    # NY state hospital financial/utilization data
    "https://www.health.ny.gov/statistics/sparcs/",
    "https://healthdata.gov/",
    "https://www.health.ny.gov/facilities/hospital/",
    # News / market position
    "https://www.crainsnewyork.com/health-pulse",
    "https://www.beckershospitalreview.com/",
    "https://www.modernhealthcare.com/providers",
]

CMS_SEEDS = [
    "https://www.cms.gov/medicare/payment/fee-schedules",
    "https://www.cms.gov/medicare/physician-fee-schedule",
    "https://www.cms.gov/medicare/payment/prospective-payment-systems",
    "https://www.cms.gov/medicare/regulations-guidance",
    "https://www.cms.gov/priorities/key-initiatives/hospital-price-transparency",
    "https://www.cms.gov/data-research/statistics-trends-reports",
    "https://www.hhs.gov/guidance/document/no-surprises-act",
    "https://www.cms.gov/medicare/coding-billing/healthcare-common-procedure-system",
    "https://www.federalregister.gov/agencies/centers-for-medicare-medicaid-services",
]

ALL_SEEDS = [(u, "mt_sinai") for u in MT_SINAI_SEEDS] + [(u, "cms") for u in CMS_SEEDS]
POOLS = ("mt_sinai", "cms")

# ---------------------------------------------------------------------------
# Crawl behavior
# ---------------------------------------------------------------------------
MAX_DEPTH = 4
MAX_PAGES_PER_CYCLE = 40          # pages fetched per alternating half-cycle
MAX_PAGES_PER_DOMAIN_TOTAL = 150  # hard cap so one domain can't eat the whole frontier
CYCLE_SLEEP_S = 60 * 5

KEYWORDS = [
    "hcpcs", "cpt", "reimbursement", "fee schedule", "price transparency",
    "chargemaster", "negotiated rate", "medicare", "medicaid", "drug pricing",
    "340b", "asp", "average sales price", "cost report", "hcris", "bond",
    "financial statement", "990", "audited financial", "margin", "operating income",
    "days cash on hand", "debt covenant", "network adequacy", "in-network",
    "out-of-network", "no surprises act", "market share", "certificate of need",
    "specialty care", "tertiary care", "provider contract", "payer mix",
]

# Domains we actively want to discover more of (used to score outbound links).
PREFERRED_DOMAINS = {
    "mountsinai.org": 3.0,
    "cms.gov": 3.0,
    "federalregister.gov": 2.5,
    "healthdata.gov": 2.0,
    "health.ny.gov": 2.5,
    "propublica.org": 2.0,
    "guidestar.org": 1.5,
    "modernhealthcare.com": 1.5,
    "beckershospitalreview.com": 1.5,
    "crainsnewyork.com": 1.5,
    "emma.msrb.org": 2.0,
    "hhs.gov": 2.0,
    "sec.gov": 1.5,
}

DOMAIN_BLOCKLIST = {
    "facebook.com", "twitter.com", "x.com", "instagram.com", "linkedin.com",
    "youtube.com", "tiktok.com", "pinterest.com",
}

CRAWL_POLICY = CrawlPolicy(
    keywords=KEYWORDS,
    preferred_domains=PREFERRED_DOMAINS,
    domain_blocklist=DOMAIN_BLOCKLIST,
    user_agent="CignaMtSinaiLeverageBot/0.1 (+research; contact: matanitah212@gmail.com)",
    request_timeout_s=20,
    request_delay_s=1.5,
    respect_robots_txt=True,
    min_link_score_to_queue=0.3,
)

# ---------------------------------------------------------------------------
# Leverage scoring dimensions
# ---------------------------------------------------------------------------
LEVERAGE_DIMENSIONS = [
    "market_network",     # local market share / network adequacy pressure
    "financial",          # margins, payer mix, days cash on hand, debt covenants
    "regulatory_pricing", # CMS benchmark rates, price transparency, No Surprises Act exposure
    "clinical_uniqueness",# tertiary/specialty exclusivity vs. commodity service
]

# Scale for each dimension score: -5 (fully favors Cigna) .. 0 (neutral) .. +5 (fully favors Mt Sinai)
SCORE_MIN, SCORE_MAX = -5, 5


def build_definition(cfg):
    """Constructs the AgentDefinition the shared loop runner needs, bound to
    this agent's single shared instance (so extract/score/wiki can read
    cfg.wiki_dir etc.)."""
    from agent_spark_core.llm import LLMClient

    from agent_def import extract, scoring, wiki

    llm = LLMClient(host=OLLAMA_HOST, model=MODEL, timeout_s=LLM_TIMEOUT_S, ctx=LLM_CTX)

    class Definition:
        pools = POOLS
        seeds = ALL_SEEDS
        crawl_policy = CRAWL_POLICY
        max_depth = MAX_DEPTH
        max_pages_per_cycle = MAX_PAGES_PER_CYCLE
        max_pages_per_domain_total = MAX_PAGES_PER_DOMAIN_TOTAL
        cycle_sleep_s = CYCLE_SLEEP_S
        dimension_names = LEVERAGE_DIMENSIONS

        def extract_facts(self, text, source_url, pool):
            return extract.extract_facts(llm, text, source_url, pool)

        def score_entity(self, store, entity):
            return scoring.score_entity(llm, store, entity)

        def rebuild_wiki(self, store, cfg_):
            return wiki.rebuild_all(store, cfg_)

    return Definition()
