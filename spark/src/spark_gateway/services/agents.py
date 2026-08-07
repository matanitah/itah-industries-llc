"""
Bridges the portal's "start/stop/open my agent" actions to the agent-spark
pattern (agent-spark/core + agent-spark/agents/<slug>) living on this same
Spark box.

Every agent has exactly **one shared instance** -- one crawl-loop process,
one SQLite DB, one wiki, one Streamlit dashboard process -- used by every
customer entitled to it (see agent-spark/core's instance.py module
docstring). What's still per-customer is *authorization*, not data:

  - control_plane.customer_has_agent(customer_id, agent_slug) -- "is this
    customer entitled to this agent at all", backed by DynamoDB, checked by
    the BFF and again here before starting/stopping anything or minting a
    dashboard token.
  - AgentToken -- a short-lived HMAC-signed token (customer_id, agent_slug,
    exp) minted by /v1/agents/{slug}/dashboard-url (which already checked the
    entitlement) and re-verified by the reverse proxy on every iframe
    request/WebSocket connect. `customer_id` rides along in the token purely
    so we can prove *this specific customer* was entitled *at mint time* --
    it does not select which instance's data gets shown, because there is
    only one. This is what lets the browser's iframe hit spark-gateway
    directly over the Cloudflare Tunnel -- bypassing API Gateway, since
    Streamlit's WebSocket traffic can't tunnel through an HTTP API's
    HTTP_PROXY integration -- without re-deriving the session cookie (which
    belongs to the website's Next.js host, not this one).

Starting/stopping the crawl loop shells out to `uv run python -m
agent_def.run_loop` inside that agent's own directory (so its own venv/deps
are used) -- exactly what agent_spark_core.procmgr expects, just invoked from
a different parent process (spark-gateway instead of that agent's own
Streamlit dashboard). The Streamlit dashboard process itself (what the
iframe actually shows) is started/stopped the same way, once per agent, on
its declared port.
"""

from __future__ import annotations

import hashlib
import hmac
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spark_gateway.config import Settings

# Keep in sync with control_plane.AGENT_SLUGS (which is what the admin UI
# offers to grant) -- this is what actually gets run when the portal opens one.
AGENT_SLUGS = ("cigna-mtsinai-negotiation", "animal-rights-watch", "cigna-actuarial-agent")

TOKEN_TTL_S = 300  # iframe re-requests a fresh token each portal page load


class AgentError(Exception):
    pass


@dataclass(frozen=True)
class AgentToken:
    customer_id: str
    agent_slug: str
    exp: int


class AgentRegistry:
    def __init__(self, settings: Settings):
        self.settings = settings
        root = settings.agent_spark_root or str(
            Path(__file__).resolve().parents[4] / "agent-spark"
        )
        self.agent_spark_root = Path(root)
        self._secret = (settings.agent_dashboard_token_secret or settings.edge_shared_token or "").encode(
            "utf-8"
        )

    # --- filesystem / instance resolution --------------------------------

    def agent_dir(self, agent_slug: str) -> Path:
        if agent_slug not in AGENT_SLUGS:
            raise AgentError(f"unknown agent_slug: {agent_slug}")
        d = self.agent_spark_root / "agents" / agent_slug
        if not d.is_dir():
            raise AgentError(
                f"agent '{agent_slug}' not found on this box at {d} "
                f"(expected agent-spark checkout at {self.agent_spark_root})"
            )
        return d

    def _config(self, agent_slug: str):
        # Imported lazily: agent_spark_core is a path/editable dependency of
        # each agent, not necessarily importable until we've confirmed the
        # checkout exists (clearer error message than an ImportError).
        from agent_spark_core import instance as instance_mod

        return instance_mod.resolve(agent_slug, self.agent_dir(agent_slug))

    def status(self, agent_slug: str) -> dict[str, Any]:
        from agent_spark_core import procmgr

        cfg = self._config(agent_slug)
        running, pid = procmgr.is_running(cfg)
        return {
            "agent_slug": agent_slug,
            "running": running,
            "pid": pid,
            "uptime_seconds": procmgr.uptime_seconds(cfg) if running else None,
            "port": cfg.port,
            "wiki_repo_url": cfg.wiki_repo_url,
        }

    def start(self, agent_slug: str) -> dict[str, Any]:
        """Starts the one shared crawl-loop process for this agent. Shared by
        every customer entitled to it -- if already running (started by this
        customer or another), this is a no-op."""
        from agent_spark_core import procmgr

        cfg = self._config(agent_slug)
        # Explicitly threaded through rather than relying on this process's
        # own OS environment already having it: spark-gateway may be started
        # by a supervisor/systemd unit that only points --env-file at .env
        # for *this* process, and subprocess.Popen only inherits what its
        # parent's OS environment holds, not what pydantic Settings parsed.
        extra_env = {}
        if self.settings.agent_spark_github_token:
            extra_env["AGENT_SPARK_GITHUB_TOKEN"] = self.settings.agent_spark_github_token
        ok, msg = procmgr.start("agent_def.run_loop", str(self.agent_dir(agent_slug)), cfg, extra_env=extra_env)
        return {"ok": ok, "message": msg, **self.status(agent_slug)}

    def stop(self, agent_slug: str) -> dict[str, Any]:
        """Stops the one shared crawl-loop process for this agent -- affects
        every customer entitled to it, not just the caller."""
        from agent_spark_core import procmgr

        cfg = self._config(agent_slug)
        ok, msg = procmgr.stop(cfg)
        return {"ok": ok, "message": msg, **self.status(agent_slug)}

    # --- Streamlit dashboard process (what the iframe displays) ----------

    def _dashboard_pid_file(self, agent_slug: str) -> Path:
        cfg = self._config(agent_slug)
        return cfg.agent_root / "logs" / "dashboard.pid"

    def dashboard_port(self, agent_slug: str) -> int:
        cfg = self._config(agent_slug)
        if not cfg.port:
            raise AgentError(f"no port declared in {self.agent_dir(agent_slug)}/agent.yaml")
        return cfg.port

    def ensure_dashboard_running(self, agent_slug: str) -> int:
        """Idempotently starts this agent's one shared Streamlit dashboard
        process (separate from the crawl-loop process) on its declared port,
        headless, bound to localhost only -- the reverse proxy is the only
        thing that talks to it. Returns the port."""
        import psutil

        port = self.dashboard_port(agent_slug)
        pid_file = self._dashboard_pid_file(agent_slug)
        pid_file.parent.mkdir(parents=True, exist_ok=True)

        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                if psutil.pid_exists(pid) and "streamlit" in " ".join(psutil.Process(pid).cmdline()):
                    return port
            except (ValueError, OSError, psutil.NoSuchProcess):
                pass

        agent_dir = self.agent_dir(agent_slug)
        stdout_log = agent_dir / "logs" / "dashboard.log"
        stdout_log.parent.mkdir(parents=True, exist_ok=True)

        with open(stdout_log, "a") as out:
            proc = subprocess.Popen(
                [
                    "uv", "run", "streamlit", "run", "dashboard.py",
                    "--server.address", "127.0.0.1",
                    "--server.port", str(port),
                    "--server.headless", "true",
                    "--server.enableCORS", "false",
                    "--server.enableXsrfProtection", "false",
                    "--browser.gatherUsageStats", "false",
                ],
                cwd=str(agent_dir),
                stdout=out,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        pid_file.write_text(str(proc.pid))
        return port

    # --- iframe tokens -----------------------------------------------------

    def mint_token(self, customer_id: str, agent_slug: str) -> str:
        if not self._secret:
            raise AgentError(
                "AGENT_DASHBOARD_TOKEN_SECRET (or EDGE_SHARED_TOKEN) is not configured on this box"
            )
        exp = int(time.time()) + TOKEN_TTL_S
        payload = f"{customer_id}:{agent_slug}:{exp}"
        sig = hmac.new(self._secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{payload}:{sig}"

    def verify_token(self, token: str) -> AgentToken:
        if not self._secret:
            raise AgentError("token verification unavailable: no secret configured")
        try:
            customer_id, agent_slug, exp_str, sig = token.split(":", 3)
            exp = int(exp_str)
        except (ValueError, TypeError) as e:
            raise AgentError("malformed token") from e

        payload = f"{customer_id}:{agent_slug}:{exp}"
        expected = hmac.new(self._secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            raise AgentError("invalid token signature")
        if exp < time.time():
            raise AgentError("token expired")
        return AgentToken(customer_id=customer_id, agent_slug=agent_slug, exp=exp)


def python_executable_hint() -> str:
    return sys.executable
