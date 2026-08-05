"""
Start/stop/status control for one agent's single shared background
run_loop.py process, driven from that agent's Streamlit dashboard (a
separate process, so control happens via a PID file + signals rather than
in-memory state).

Every function takes an `AgentConfig` explicitly (rather than reading a
module-level singleton) so this stays agent-agnostic, but there is exactly
one instance -- and therefore one PID file -- per agent, shared by every
customer entitled to it (see instance.py's module docstring).
"""

import os
import subprocess
import time

import psutil

from agent_spark_core.instance import AgentConfig, ensure_dirs


def is_running(cfg: AgentConfig) -> tuple[bool, int | None]:
    """Returns (running, pid). Verifies the PID is actually our process, not a
    reused PID belonging to something else."""
    if not cfg.pid_file.exists():
        return False, None
    try:
        pid = int(cfg.pid_file.read_text().strip())
    except (ValueError, OSError):
        return False, None

    if not psutil.pid_exists(pid):
        return False, None

    try:
        proc = psutil.Process(pid)
        cmdline = " ".join(proc.cmdline())
        if "run_loop" not in cmdline:
            return False, None
        if proc.status() == psutil.STATUS_ZOMBIE:
            return False, None
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    return True, pid


def start(run_loop_module: str, cwd: str, cfg: AgentConfig, extra_env: dict | None = None) -> tuple[bool, str]:
    """Launch `python -m {run_loop_module}`, detached from the dashboard
    process's session. Shared across every customer entitled to this agent --
    if it's already running (started by this customer, another customer, or
    the dashboard's auto-start), this is a no-op.

    Always launched via `uv run` scoped to the *target agent's own*
    directory/venv (`--project cwd`), never via `sys.executable` -- this
    function can be called from a process running in a completely different
    venv than the agent being started (spark-gateway's AgentRegistry does
    exactly this: it launches N different agents, each with their own
    dependency set, from spark-gateway's own venv). Using sys.executable
    there would run the target agent's code under spark-gateway's
    interpreter/dependencies, which only accidentally "works" for whatever
    happens to be importable via cwd-based sys.path and silently breaks for
    anything that actually needs the target agent's installed dependencies.

    `extra_env` is merged on top of this process's own environment before
    launch -- notably AGENT_SPARK_GITHUB_TOKEN when the caller is
    spark-gateway (a long-running daemon whose own env may not already carry
    it; see spark_gateway/services/agents.py) rather than a human's shell
    that already has it exported."""
    running, pid = is_running(cfg)
    if running:
        return False, f"Already running (PID {pid})"

    ensure_dirs(cfg)
    env = {**os.environ, **(extra_env or {})}
    with open(cfg.stdout_log, "a") as out:
        proc = subprocess.Popen(
            ["uv", "run", "--project", cwd, "python", "-u", "-m", run_loop_module],
            cwd=cwd,
            env=env,
            stdout=out,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,  # detach from this (dashboard) process's session
        )
    cfg.pid_file.write_text(str(proc.pid))
    return True, f"Started (PID {proc.pid})"


def stop(cfg: AgentConfig, timeout_s: float = 30) -> tuple[bool, str]:
    """Stops the shared instance for everyone entitled to this agent -- there
    is only one process, not a per-customer one (see instance.py)."""
    running, pid = is_running(cfg)
    if not running:
        return False, "Not running"

    try:
        proc = psutil.Process(pid)
        proc.terminate()  # SIGTERM -> run_loop's handler finishes current page, exits cleanly
    except psutil.NoSuchProcess:
        cfg.pid_file.unlink(missing_ok=True)
        return True, "Was already stopped"

    waited = 0.0
    while waited < timeout_s:
        if not psutil.pid_exists(pid):
            cfg.pid_file.unlink(missing_ok=True)
            return True, f"Stopped cleanly (PID {pid})"
        time.sleep(0.5)
        waited += 0.5

    # Didn't exit in time -- force kill.
    try:
        proc = psutil.Process(pid)
        proc.kill()
    except psutil.NoSuchProcess:
        pass
    cfg.pid_file.unlink(missing_ok=True)
    return True, f"Did not stop gracefully within {timeout_s}s, force-killed (PID {pid})"


def tail_log(cfg: AgentConfig, n_lines: int = 200) -> str:
    if not cfg.stdout_log.exists():
        return "(no log yet)"
    try:
        with open(cfg.stdout_log, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        return "".join(lines[-n_lines:])
    except OSError as e:
        return f"(error reading log: {e})"


def uptime_seconds(cfg: AgentConfig) -> float | None:
    running, pid = is_running(cfg)
    if not running:
        return None
    try:
        proc = psutil.Process(pid)
        return time.time() - proc.create_time()
    except psutil.NoSuchProcess:
        return None
