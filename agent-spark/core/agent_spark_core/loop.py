"""
Generic long-running loop driver shared by every agent's run_loop.py.

Alternates between an agent's pool names each half-cycle, fetching/extracting/
scoring/rebuilding-wiki exactly like the original leverage-agent, but with the
domain-specific pieces (extraction prompt, scoring prompt, wiki renderer,
pools, seeds) supplied by the concrete agent through the `AgentDefinition`
protocol below. Safe to kill/restart at any point: state lives in SQLite, the
wiki is regenerated from state (not incrementally patched), and wiki commits
are pushed to the agent's shared GitHub repo once per cycle -- there is one
instance of each agent, shared by every customer entitled to it (see
instance.py's module docstring).
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from dataclasses import dataclass
from typing import Callable, Protocol
from urllib.parse import urlparse

from agent_spark_core import healthcheck, wiki_git
from agent_spark_core.crawler import CrawlPolicy, fetch, score_link
from agent_spark_core.instance import AgentConfig, ensure_dirs
from agent_spark_core.state import Store

log = logging.getLogger("agent_spark_core.loop")

HEALTHCHECK_INTERVAL_S = 3600


class AgentDefinition(Protocol):
    """What a concrete agent (e.g. cigna-mtsinai-negotiation) provides to run
    the generic loop. Implemented as a plain module in each agent's
    `agent_def/run_loop.py` that constructs one of these from its own config.
    """

    pools: tuple[str, str]
    seeds: list[tuple[str, str]]          # (url, pool)
    crawl_policy: CrawlPolicy
    max_depth: int
    max_pages_per_cycle: int
    max_pages_per_domain_total: int
    cycle_sleep_s: int
    dimension_names: list[str]

    def extract_facts(self, text: str, source_url: str, pool: str) -> list[dict]:
        """-> [{"entity": str, "dimension": str|None, "fact": str}, ...]"""
        ...

    def score_entity(self, store: Store, entity: str) -> list[dict]:
        """Re-score one entity from its accumulated facts; upserts into store."""
        ...

    def rebuild_wiki(self, store: Store, cfg: AgentConfig) -> None:
        """Regenerate all wiki markdown from current DB state."""
        ...


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


@dataclass
class LoopRunner:
    cfg: AgentConfig
    store: Store
    definition: AgentDefinition
    _shutdown: bool = False

    def _handle_signal(self, signum, frame):
        log.info("received signal %s, will stop after current page", signum)
        self._shutdown = True

    def process_url(self, row, pool: str) -> set[str] | None:
        url = row["url"]
        domain = _domain(url)
        d = self.definition

        if self.store.domain_count(domain) >= d.max_pages_per_domain_total:
            self.store.mark_status(url, "skipped")
            return None

        if self.store.is_visited(url):
            self.store.mark_status(url, "done")
            return None

        result = fetch(d.crawl_policy, url)
        if result is None:
            self.store.mark_status(url, "failed")
            return None

        self.store.increment_domain_count(domain)
        self.store.record_visit(url, pool, result.status_code, result.content_hash, result.title)

        if result.status_code != 200 or not result.text:
            self.store.mark_status(url, "failed")
            return None

        log.info("[%s] fetched (%d chars) %s — %s", pool, len(result.text), url, result.title[:80])

        touched: set[str] = set()
        facts = d.extract_facts(result.text, url, pool)
        for f in facts:
            self.store.add_fact(f["entity"], pool, f.get("dimension"), f["fact"], url)
            touched.add(f["entity"])
        if facts:
            log.info("  extracted %d facts (entities: %s)", len(facts), ", ".join(sorted(touched)) or "-")

        queued = 0
        for link_url, anchor_text in result.links:
            link_domain = _domain(link_url)
            if link_domain in d.crawl_policy.domain_blocklist:
                continue
            if self.store.domain_count(link_domain) >= d.max_pages_per_domain_total:
                continue
            if row["depth"] >= d.max_depth:
                continue
            score = score_link(d.crawl_policy, link_url, anchor_text)
            if score < d.crawl_policy.min_link_score_to_queue:
                continue
            self.store.enqueue(link_url, pool, row["depth"] + 1, score)
            queued += 1
        if queued:
            log.info("  queued %d new links", queued)

        self.store.mark_status(url, "done")
        return touched

    def run_half_cycle(self, pool: str) -> set[str]:
        d = self.definition
        batch = self.store.next_batch(pool, d.max_pages_per_cycle)
        if not batch:
            log.info("[%s] frontier empty for this pool", pool)
            return set()

        log.info("[%s] processing batch of %d URLs", pool, len(batch))
        touched: set[str] = set()
        for row in batch:
            if self._shutdown:
                break
            try:
                entities = self.process_url(row, pool)
                if entities:
                    touched |= entities
            except Exception:
                log.exception("unhandled error processing %s", row["url"])
                self.store.mark_status(row["url"], "failed")
        return touched

    def run(self):
        d = self.definition
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        ensure_dirs(self.cfg)
        self.cfg.pid_file.write_text(str(os.getpid()))

        self.store.init_db()
        self.store.seed_frontier(d.seeds)
        wiki_git.ensure_clone(self.cfg.wiki_dir, self.cfg.wiki_repo_url)
        log.info("agent starting for %s. stats=%s", self.cfg.agent_slug, self.store.stats())

        cycle = 0
        last_healthcheck = time.time()
        while not self._shutdown:
            cycle += 1
            log.info("=== cycle %d ===", cycle)

            all_touched: set[str] = set()
            for pool in d.pools:
                if self._shutdown:
                    break
                all_touched |= self.run_half_cycle(pool)

            for entity in all_touched:
                if entity == "GENERAL" or self._shutdown:
                    continue
                try:
                    d.score_entity(self.store, entity)
                except Exception:
                    log.exception("scoring failed for %s", entity)

            try:
                d.rebuild_wiki(self.store, self.cfg)
                wiki_git.commit_and_push(
                    self.cfg.wiki_dir,
                    self.cfg.wiki_repo_url,
                    f"cycle {cycle}: {self.store.stats()['entities']} entities, {self.store.stats()['facts']} facts",
                )
            except Exception:
                log.exception("wiki rebuild/push failed")

            log.info("cycle %d done. stats=%s", cycle, self.store.stats())

            if time.time() - last_healthcheck >= HEALTHCHECK_INTERVAL_S:
                try:
                    healthcheck.run_healthcheck(self.cfg, self.store, d.dimension_names)
                except Exception:
                    log.exception("healthcheck run failed")
                last_healthcheck = time.time()

            if self._shutdown:
                break
            log.info("sleeping %ds before next cycle", d.cycle_sleep_s)
            for _ in range(d.cycle_sleep_s):
                if self._shutdown:
                    break
                time.sleep(1)

        try:
            healthcheck.run_healthcheck(self.cfg, self.store, d.dimension_names)
        except Exception:
            log.exception("final healthcheck run failed")

        self.cfg.pid_file.unlink(missing_ok=True)
        log.info("agent shutting down cleanly. final stats=%s", self.store.stats())


def main(
    *,
    agent_slug: str,
    agent_root,
    build_definition: Callable[[AgentConfig], AgentDefinition],
):
    """Standard entrypoint body for a concrete agent's `run_loop.py`:

        if __name__ == "__main__":
            loop.main(agent_slug="cigna-mtsinai-negotiation", agent_root=..., build_definition=build_definition)

    There is exactly one shared instance per agent (see instance.py) -- no
    per-customer parameter is needed here, unlike start/stop which is still
    gated per customer by the portal's entitlement check upstream.
    """
    from agent_spark_core import instance as instance_mod

    cfg = instance_mod.resolve(agent_slug, agent_root)
    ensure_dirs(cfg)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(cfg.log_file)],
    )

    store = Store(cfg.state_db)
    definition = build_definition(cfg)
    LoopRunner(cfg=cfg, store=store, definition=definition).run()
