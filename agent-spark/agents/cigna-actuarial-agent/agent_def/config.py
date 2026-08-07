"""
Domain configuration for the Cigna actuarial medical-cost-trend agent.

Three seed pools feed one crawl frontier:
  - PHARMACY_SEEDS: drug pricing / specialty pharmacy / PBM & rebate signal
  - MEDICAL_SEEDS: hospital & facility cost, utilization, unit-cost signal
  - REGULATORY_SEEDS: CMS reimbursement, state mandates, coverage rule signal

Unlike cigna-mtsinai-negotiation (which tracks leverage for one payer/provider
pair on individual HCPCS codes), this agent tracks *trend drivers* -- named
cost themes (e.g. "GLP-1 drug spend", "CMS 2026 conversion factor") -- the
kind of inputs an actuary would fold into next year's trend assumption. It is
Cigna-specific in framing (facts and scores are written from the perspective
of "what should this change to Cigna's medical cost trend assumption") but is
not tied to any single provider negotiation.

Crawling is "open-ended" in the sense that discovered links are followed, but
every discovered domain is scored for relevance before being queued (see
agent_spark_core.crawler), and off-topic domains decay out of the frontier
quickly. Structurally this module mirrors cigna-mtsinai-negotiation/agent_def/
config.py -- see that file's docstring for the shared plumbing.
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
PHARMACY_SEEDS = [
    # Drug pricing / ASP / specialty pharmacy
    "https://www.cms.gov/medicare/payment/part-b-drugs/asp-pricing-files",
    "https://www.ashp.org/drug-shortages/current-shortages",
    "https://www.fiercepharma.com/pharma",
    "https://www.biopharmadive.com/topic/regulatory-fda/",
    # PBM / rebate / formulary
    "https://www.ncpa.org/newsroom/qam",
    "https://www.drugchannels.net/",
    # GLP-1 / specialty drug spend trend
    "https://www.ajmc.com/channels/specialty-pharmacy",
    "https://www.fda.gov/drugs/drug-approvals-and-databases/new-drugs-fda-cders-new-molecular-entities-and-new-therapeutic-biological-products",
]

MEDICAL_SEEDS = [
    # Facility / hospital cost & utilization trend
    "https://www.healthcostinstitute.org/research",
    "https://www.beckershospitalreview.com/finance.html",
    "https://www.modernhealthcare.com/finance",
    "https://www.ahajournals.org/",
    "https://healthdata.gov/",
    # Employer / payer trend reports (pre-digested, high-signal)
    "https://www.milliman.com/en/insight?filter=health",
    "https://www.pwc.com/us/en/industries/health-industries/behind-the-numbers.html",
    "https://www.segalco.com/consulting-insights/health-plan-cost-trend/",
    "https://www.kff.org/health-costs/",
]

REGULATORY_SEEDS = [
    "https://www.cms.gov/medicare/payment/fee-schedules",
    "https://www.cms.gov/medicare/physician-fee-schedule",
    "https://www.cms.gov/medicare/payment/prospective-payment-systems",
    "https://www.cms.gov/medicare/regulations-guidance",
    "https://www.cms.gov/priorities/key-initiatives/hospital-price-transparency",
    "https://www.cms.gov/data-research/statistics-trends-reports",
    "https://www.federalregister.gov/agencies/centers-for-medicare-medicaid-services",
    "https://www.naic.org/index_health.htm",  # state mandate / coverage rule signal
]

ALL_SEEDS = (
    [(u, "pharmacy") for u in PHARMACY_SEEDS]
    + [(u, "medical") for u in MEDICAL_SEEDS]
    + [(u, "regulatory") for u in REGULATORY_SEEDS]
)
POOLS = ("pharmacy", "medical", "regulatory")

# ---------------------------------------------------------------------------
# Crawl behavior
# ---------------------------------------------------------------------------
MAX_DEPTH = 4
MAX_PAGES_PER_CYCLE = 30          # pages fetched per pool per cycle (3 pools vs. sibling's 2)
MAX_PAGES_PER_DOMAIN_TOTAL = 150  # hard cap so one domain can't eat the whole frontier
CYCLE_SLEEP_S = 60 * 5

KEYWORDS = [
    "medical cost trend", "trend assumption", "unit cost", "utilization",
    "specialty drug", "glp-1", "rebate", "pbm", "formulary", "asp",
    "average sales price", "list price", "wac", "wholesale acquisition cost",
    "hcpcs", "cpt", "reimbursement", "fee schedule", "conversion factor",
    "prospective payment", "price transparency", "chargemaster",
    "negotiated rate", "medicare", "medicaid", "340b", "site of service",
    "cost report", "hcris", "per member per month", "pmpm", "actuarial",
    "premium trend", "loss ratio", "drug shortage", "biosimilar",
    "patent cliff", "state mandate", "coverage mandate", "no surprises act",
]

# Domains we actively want to discover more of (used to score outbound links).
PREFERRED_DOMAINS = {
    "cms.gov": 3.0,
    "federalregister.gov": 2.5,
    "healthdata.gov": 2.0,
    "healthcostinstitute.org": 2.5,
    "milliman.com": 2.5,
    "kff.org": 2.5,
    "pwc.com": 1.5,
    "segalco.com": 2.0,
    "drugchannels.net": 2.0,
    "ajmc.com": 1.5,
    "fiercepharma.com": 1.5,
    "biopharmadive.com": 1.5,
    "modernhealthcare.com": 1.5,
    "beckershospitalreview.com": 1.5,
    "fda.gov": 2.0,
    "ashp.org": 1.5,
    "naic.org": 1.5,
    "ncpa.org": 1.0,
}

DOMAIN_BLOCKLIST = {
    "facebook.com", "twitter.com", "x.com", "instagram.com", "linkedin.com",
    "youtube.com", "tiktok.com", "pinterest.com",
}

CRAWL_POLICY = CrawlPolicy(
    keywords=KEYWORDS,
    preferred_domains=PREFERRED_DOMAINS,
    domain_blocklist=DOMAIN_BLOCKLIST,
    user_agent="CignaActuarialTrendBot/0.1 (+research; contact: matanitah212@gmail.com)",
    request_timeout_s=20,
    request_delay_s=1.5,
    respect_robots_txt=True,
    min_link_score_to_queue=0.3,
)

# ---------------------------------------------------------------------------
# Trend scoring dimensions
# ---------------------------------------------------------------------------
TREND_DIMENSIONS = [
    "direction",      # -5 strongly deflationary .. 0 neutral .. +5 strongly inflationary
    "magnitude",       # 0 (negligible) .. 5 (material, moves the trend assumption meaningfully)
    "confidence",      # 0 (rumor/single weak source) .. 5 (well-corroborated, multiple strong sources)
    "time_horizon",    # -5 (already realized/near-term, e.g. this plan year) .. +5 (long-term/speculative signal)
]

# Scale for each dimension score.
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
        dimension_names = TREND_DIMENSIONS

        def extract_facts(self, text, source_url, pool):
            return extract.extract_facts(llm, text, source_url, pool)

        def score_entity(self, store, entity):
            return scoring.score_entity(llm, store, entity)

        def rebuild_wiki(self, store, cfg_):
            return wiki.rebuild_all(store, cfg_)

    return Definition()
