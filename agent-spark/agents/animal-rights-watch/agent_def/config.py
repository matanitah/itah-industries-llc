"""
Domain configuration for the animal-rights-watch agent.

Two seed pools feed one crawl frontier, mirroring cigna-mtsinai-negotiation's
two-pool alternation:
  - VIOLATIONS_SEEDS: investigative/advocacy/regulatory reporting on systemic
    animal-rights violations (factory farming, labs, transport, puppy mills,
    roadside zoos, etc) tied to a specific company/facility/operator.
  - CASE_LAW_SEEDS: state legislature, court-opinion, and law-review/tracker
    sources for animal-cruelty and animal-rights case law across all 50
    states, tied to a specific case name.

Crawling is "open-ended": discovered links are followed, but every discovered
domain is scored for relevance before being queued (see
agent_spark_core.crawler), and off-topic domains decay out of the frontier
quickly.
"""

from agent_spark_core.crawler import CrawlPolicy

# ---------------------------------------------------------------------------
# LLM (local, via ollama)
# ---------------------------------------------------------------------------
OLLAMA_HOST = "http://127.0.0.1:11434"
MODEL = "gpt-oss:20b"
LLM_TIMEOUT_S = 300
LLM_CTX = 8192

# ---------------------------------------------------------------------------
# Seed sources
# ---------------------------------------------------------------------------
VIOLATIONS_SEEDS = [
    # Federal regulatory enforcement records
    "https://www.aphis.usda.gov/aphis/newsroom/stakeholder-info",       # USDA-APHIS Animal Welfare Act enforcement
    "https://www.aphis.usda.gov/animal-welfare/ac-enforcement-actions",
    "https://www.fws.gov/law-enforcement",                              # Fish & Wildlife Service enforcement
    "https://www.epa.gov/afo",                                          # Animal feeding operations / factory farm environmental enforcement
    # Investigative / advocacy reporting (systemic patterns, not one-offs)
    "https://www.animalequality.org/investigations/",
    "https://www.mercyforanimals.org/investigations",
    "https://www.humanesociety.org/all-our-fights/investigating-animal-cruelty",
    "https://aldf.org/case/",                                           # Animal Legal Defense Fund case tracker
    "https://www.peta.org/investigations/",
    "https://sentientmedia.org/category/investigations/",
    # News covering systemic/industrial patterns
    "https://www.foodsafetynews.com/",
    "https://civileats.com/",
    "https://www.sentienceinstitute.org/",
]

CASE_LAW_SEEDS = [
    # National case-law aggregators / trackers covering all 50 states
    "https://aldf.org/cases/",                                          # ALDF litigation docket
    "https://www.animallaw.info/cases",                                 # Michigan State animal law case database (all states)
    "https://www.courtlistener.com/?q=animal+cruelty",                  # Free Law Project opinion search
    "https://www.animallaw.info/topic/table-state-animal-cruelty-laws", # 50-state statute comparison
    "https://www.ncsl.org/agriculture-and-rural-development/animal-cruelty-and-fighting", # state legislature tracker
    "https://www.animallaw.info/topic/table-state-assistance-animal-laws",
    # Federal reporters/dockets that frequently carry animal-welfare appeals
    "https://www.courtlistener.com/?q=animal+welfare+act",
    "https://www.justia.com/animal-rights/",
]

ALL_SEEDS = [(u, "violations") for u in VIOLATIONS_SEEDS] + [(u, "case_law") for u in CASE_LAW_SEEDS]
POOLS = ("violations", "case_law")

# ---------------------------------------------------------------------------
# Crawl behavior
# ---------------------------------------------------------------------------
MAX_DEPTH = 4
MAX_PAGES_PER_CYCLE = 40
MAX_PAGES_PER_DOMAIN_TOTAL = 150
CYCLE_SLEEP_S = 60 * 5

KEYWORDS = [
    "animal cruelty", "animal welfare act", "factory farm", "cafo", "puppy mill",
    "roadside zoo", "usda inspection", "aphis violation", "undercover investigation",
    "slaughterhouse violation", "live animal transport", "downer animal", "animal fighting",
    "neglect charges", "cruelty conviction", "cruelty statute", "felony cruelty",
    "wildlife trafficking", "endangered species act", "captive wildlife", "puppy mill bill",
    "ag-gag", "right to farm", "animal sentience", "class action animal", "humane slaughter act",
    "state v.", "commonwealth v.", "people v.", "animal legal defense fund", "standing to sue",
]

PREFERRED_DOMAINS = {
    "aphis.usda.gov": 3.0,
    "fws.gov": 2.5,
    "epa.gov": 2.0,
    "aldf.org": 3.0,
    "animallaw.info": 3.0,
    "courtlistener.com": 2.5,
    "animalequality.org": 2.0,
    "mercyforanimals.org": 2.0,
    "humanesociety.org": 2.0,
    "peta.org": 1.5,
    "sentientmedia.org": 1.5,
    "sentienceinstitute.org": 1.5,
    "foodsafetynews.com": 1.5,
    "civileats.com": 1.5,
    "ncsl.org": 2.5,
    "justia.com": 2.0,
}

DOMAIN_BLOCKLIST = {
    "facebook.com", "twitter.com", "x.com", "instagram.com", "linkedin.com",
    "youtube.com", "tiktok.com", "pinterest.com",
}

CRAWL_POLICY = CrawlPolicy(
    keywords=KEYWORDS,
    preferred_domains=PREFERRED_DOMAINS,
    domain_blocklist=DOMAIN_BLOCKLIST,
    user_agent="AnimalRightsWatchBot/0.1 (+research; contact: matanitah212@gmail.com)",
    request_timeout_s=20,
    request_delay_s=1.5,
    respect_robots_txt=True,
    min_link_score_to_queue=0.3,
)

# ---------------------------------------------------------------------------
# Severity / confidence scoring dimensions
# ---------------------------------------------------------------------------
# Unlike cigna-mtsinai-negotiation's bipolar Cigna<->MtSinai scale, these are
# unipolar 0..5 severity/confidence scales -- there's no "other side" to favor,
# just how strong and how serious the evidence is for a given tracked entity
# (a company/facility/operator for the violations pool, a case for case_law).
SCORING_DIMENSIONS = [
    "evidence_strength",  # 0 = anecdotal/unsubstantiated .. 5 = documented/adjudicated/regulatory finding
    "severity",           # 0 = minor/isolated .. 5 = systemic, mass-scale, or repeated cruelty
    "legal_exposure",     # 0 = no clear statutory violation identified .. 5 = clear violation w/ enforcement history
    "recency",            # 0 = old/resolved/historical .. 5 = active/ongoing as of latest facts gathered
]

SCORE_MIN, SCORE_MAX = 0, 5


def build_definition(cfg):
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
        dimension_names = SCORING_DIMENSIONS

        def extract_facts(self, text, source_url, pool):
            return extract.extract_facts(llm, text, source_url, pool)

        def score_entity(self, store, entity):
            return scoring.score_entity(llm, store, entity)

        def rebuild_wiki(self, store, cfg_):
            return wiki.rebuild_all(store, cfg_)

    return Definition()
