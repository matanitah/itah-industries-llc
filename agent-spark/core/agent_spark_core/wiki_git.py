"""
Git-backed sync for one agent's shared wiki working tree.

Each agent writes its wiki as plain markdown files under `AgentConfig.wiki_dir`,
exactly like the original leverage-agent did -- the only new behavior here is
that this directory is *also* a git working tree pointed at one repo the admin
pre-provisioned for that agent under the `itah-industries-wikis` GitHub org
(see `instance.py`'s `agent.yaml`: `wiki_repo_url`), and every cycle that
changes anything gets committed and pushed. Every customer entitled to the
agent shares this one wiki/repo -- there is no per-customer copy.

Design choices (see conversation record for why):
  - The admin creates the GitHub repo ahead of time (one per agent, under
    `itah-industries-wikis`); this module never creates repos, only clones an
    existing one if the local working tree is missing.
  - Auth is a single fine-grained GitHub PAT for the whole Spark box
    (Contents: Read and write, scoped to the `itah-industries-wikis` org),
    read from AGENT_SPARK_GITHUB_TOKEN. It's injected into the remote URL for
    pushes only (not persisted to the git config on disk) so the token never
    lingers in a committed/inspectable file. `wiki_repo_url` must be an
    `https://github.com/...` URL for this token injection to apply -- a
    fine-grained PAT has no meaning to an `git@github.com:...` (SSH) remote.
  - The local clone is the dashboard's read path (fast, no network on page
    load). GitHub is the durable mirror / audit trail, not the read path.
  - Failures here (no token, no network, push rejected) are logged and
    swallowed by the caller's perspective -- a wiki sync problem should never
    take down the crawl loop itself.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

log = logging.getLogger("agent_spark_core.wiki_git")

GITHUB_TOKEN_ENV = "AGENT_SPARK_GITHUB_TOKEN"
GIT_AUTHOR = ("agent-spark", "agent-spark@itah-industries.llc")


class WikiGitError(Exception):
    pass


def _run(args: list[str], cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _authenticated_url(repo_url: str, token: str) -> str:
    """Inject an https token into the remote URL for a single push, without
    ever writing it to the on-disk git config (`push` takes an explicit URL
    argument rather than mutating `origin`)."""
    if repo_url.startswith("https://"):
        return repo_url.replace("https://", f"https://x-access-token:{token}@", 1)
    # git@github.com:org/repo.git (SSH) -- fine-grained PATs only authenticate
    # over HTTPS, so an SSH remote here means AGENT_SPARK_GITHUB_TOKEN is
    # silently unused for it. Use an https:// wiki_repo_url in agent.yaml.
    log.warning(
        "wiki_repo_url %s is an SSH remote; AGENT_SPARK_GITHUB_TOKEN (fine-grained PAT) only "
        "authenticates over HTTPS -- use an https://github.com/... URL instead",
        repo_url,
    )
    return repo_url


def ensure_clone(wiki_dir: Path, repo_url: str | None) -> bool:
    """Ensure `wiki_dir` is a git working tree tracking `repo_url`.

    Returns True if the directory is git-backed and usable, False if there's
    no repo configured (in which case the caller falls back to plain local
    files, matching the original leverage-agent behavior).
    """
    if not repo_url:
        return False

    if (wiki_dir / ".git").exists():
        return True

    wiki_dir.parent.mkdir(parents=True, exist_ok=True)
    token = os.environ.get(GITHUB_TOKEN_ENV, "")
    clone_url = _authenticated_url(repo_url, token) if token else repo_url

    if wiki_dir.exists() and any(wiki_dir.iterdir()):
        # Directory pre-exists with content (e.g. first run wrote files before
        # we got here) -- init in place and add the remote rather than clone.
        result = _run(["git", "init"], cwd=wiki_dir)
        if result.returncode != 0:
            log.warning("git init failed for %s: %s", wiki_dir, result.stderr)
            return False
        _run(["git", "remote", "add", "origin", repo_url], cwd=wiki_dir)
        return True

    result = _run(["git", "clone", clone_url, str(wiki_dir)], cwd=wiki_dir.parent)
    if result.returncode != 0:
        log.warning("git clone failed for %s: %s", repo_url, result.stderr.strip()[:500])
        wiki_dir.mkdir(parents=True, exist_ok=True)
        return False
    log.info("cloned wiki repo %s into %s", repo_url, wiki_dir)
    return True


def commit_and_push(wiki_dir: Path, repo_url: str | None, message: str) -> bool:
    """Stage all changes, commit if there's anything to commit, and push.

    No-ops quietly (returns False) if the directory isn't git-backed. Push
    failures are logged, not raised -- a wiki that's a cycle behind on GitHub
    is not worth stopping the crawl loop over.
    """
    if not repo_url or not (wiki_dir / ".git").exists():
        return False

    _run(["git", "add", "-A"], cwd=wiki_dir)
    status = _run(["git", "status", "--porcelain"], cwd=wiki_dir)
    if not status.stdout.strip():
        return True  # nothing changed this cycle

    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": GIT_AUTHOR[0],
        "GIT_AUTHOR_EMAIL": GIT_AUTHOR[1],
        "GIT_COMMITTER_NAME": GIT_AUTHOR[0],
        "GIT_COMMITTER_EMAIL": GIT_AUTHOR[1],
    }
    commit = _run(["git", "commit", "-m", message], cwd=wiki_dir, env=env)
    if commit.returncode != 0:
        log.warning("git commit failed for %s: %s", wiki_dir, commit.stderr.strip()[:500])
        return False

    token = os.environ.get(GITHUB_TOKEN_ENV, "")
    push_url = _authenticated_url(repo_url, token) if token else None

    branch = _run(["git", "branch", "--show-current"], cwd=wiki_dir).stdout.strip() or "main"
    push_args = ["git", "push"] + ([push_url, branch] if push_url else ["origin", branch])
    push = _run(push_args, cwd=wiki_dir, env=env)
    if push.returncode != 0:
        log.warning("git push failed for %s: %s", wiki_dir, push.stderr.strip()[:500])
        return False

    log.info("pushed wiki update to %s (%s)", repo_url, branch)
    return True
