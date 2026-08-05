"""
Fetching, robots.txt compliance, link extraction and relevance scoring.

Open-ended crawling: any link found on a fetched page can be queued, but every
link is scored first (domain preference + anchor-text/URL keyword relevance)
and low-scoring links are dropped. This keeps the frontier from wandering into
irrelevant territory while still allowing genuine discovery beyond the seed
list. The keyword list, domain weights and blocklist are supplied by the
concrete agent via `CrawlPolicy`, so this module has no domain knowledge of
its own.
"""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger("agent_spark_core.crawler")

_robots_cache: dict[str, RobotFileParser] = {}
_last_request_at: dict[str, float] = {}


@dataclass(frozen=True)
class CrawlPolicy:
    """Everything the crawler needs from the concrete agent to score/fetch politely."""

    keywords: list[str]
    preferred_domains: dict[str, float] = field(default_factory=dict)
    domain_blocklist: set[str] = field(default_factory=set)
    user_agent: str = "AgentSparkBot/0.1 (+research)"
    request_timeout_s: int = 20
    request_delay_s: float = 1.5
    respect_robots_txt: bool = True
    min_link_score_to_queue: float = 0.3


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _get_robots(policy: CrawlPolicy, url: str) -> RobotFileParser | None:
    if not policy.respect_robots_txt:
        return None
    domain = _domain(url)
    if domain in _robots_cache:
        return _robots_cache[domain]
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = RobotFileParser()
    try:
        resp = httpx.get(robots_url, timeout=10, headers={"User-Agent": policy.user_agent})
        if resp.status_code == 200:
            rp.parse(resp.text.splitlines())
        else:
            rp = None  # no robots.txt -> allow
    except httpx.HTTPError:
        rp = None
    _robots_cache[domain] = rp
    return rp


def _allowed(policy: CrawlPolicy, url: str) -> bool:
    rp = _get_robots(policy, url)
    if rp is None:
        return True
    return rp.can_fetch(policy.user_agent, url)


def _politeness_wait(policy: CrawlPolicy, url: str):
    domain = _domain(url)
    last = _last_request_at.get(domain, 0)
    elapsed = time.time() - last
    if elapsed < policy.request_delay_s:
        time.sleep(policy.request_delay_s - elapsed)
    _last_request_at[domain] = time.time()


def score_link(policy: CrawlPolicy, url: str, anchor_text: str) -> float:
    """Heuristic relevance score for an outbound link."""
    domain = _domain(url)
    if domain in policy.domain_blocklist:
        return 0.0

    score = policy.preferred_domains.get(domain, 0.5)

    haystack = f"{url} {anchor_text}".lower()
    hits = sum(1 for kw in policy.keywords if kw in haystack)
    score += hits * 0.4

    # Penalize obvious non-content links
    if any(url.lower().endswith(ext) for ext in (".jpg", ".png", ".gif", ".css", ".js", ".ico", ".svg")):
        return 0.0
    if any(seg in url.lower() for seg in ("/login", "/signin", "/cart", "/donate", "mailto:", "tel:")):
        return 0.0

    return score


class FetchResult:
    def __init__(self, url: str, status_code: int, text: str, title: str, links: list[tuple[str, str]]):
        self.url = url
        self.status_code = status_code
        self.text = text
        self.title = title
        self.links = links  # list of (absolute_url, anchor_text)
        self.content_hash = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def fetch(policy: CrawlPolicy, url: str) -> FetchResult | None:
    if not _allowed(policy, url):
        log.info("robots.txt disallows %s", url)
        return None

    # Per-domain page cap is enforced by the caller (run_loop.py) via state.domain_count,
    # since that requires DB access this module doesn't own.
    _politeness_wait(policy, url)

    try:
        with httpx.Client(follow_redirects=True, timeout=policy.request_timeout_s) as client:
            resp = client.get(url, headers={"User-Agent": policy.user_agent})
    except httpx.HTTPError as e:
        log.warning("fetch failed %s: %s", url, e)
        return None

    if resp.status_code != 200:
        log.info("non-200 (%s) for %s", resp.status_code, url)
        return FetchResult(url, resp.status_code, "", "", [])

    content_type = resp.headers.get("content-type", "")

    if "application/pdf" in content_type or url.lower().endswith(".pdf"):
        text = _extract_pdf_text(resp.content)
        return FetchResult(url, resp.status_code, text, title=url.rsplit("/", 1)[-1], links=[])

    if "text/html" not in content_type and not content_type.startswith("text/"):
        log.info("skipping non-HTML content-type %s for %s", content_type, url)
        return FetchResult(url, resp.status_code, "", "", [])

    soup = BeautifulSoup(resp.text, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "noscript"]):
        tag.decompose()

    title = soup.title.get_text(strip=True) if soup.title else url
    text = soup.get_text(separator="\n", strip=True)

    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue
        abs_url = urljoin(url, href)
        parsed = urlparse(abs_url)
        if parsed.scheme not in ("http", "https"):
            continue
        abs_url = parsed._replace(fragment="").geturl()
        links.append((abs_url, a.get_text(strip=True)[:200]))

    return FetchResult(url, resp.status_code, text, title, links)


def _extract_pdf_text(content: bytes) -> str:
    try:
        import io

        from PyPDF2 import PdfReader

        reader = PdfReader(io.BytesIO(content))
        pages = []
        for i, page in enumerate(reader.pages):
            if i >= 40:  # cap very long filings
                break
            try:
                pages.append(page.extract_text() or "")
            except Exception:
                continue
        return "\n".join(pages)
    except Exception as e:
        log.warning("PDF extraction failed: %s", e)
        return ""
