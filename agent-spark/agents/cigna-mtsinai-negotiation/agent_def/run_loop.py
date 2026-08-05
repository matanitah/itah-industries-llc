"""
Entrypoint for the background crawl loop, launched by the dashboard's Start
button (agent_spark_core.procmgr.start) as:

    python -m agent_def.run_loop

There is exactly one shared instance of this agent (see
agent_spark_core/instance.py), used by every customer entitled to it. All the
actual loop mechanics live in agent_spark_core.loop; this module only
supplies the domain wiring via config.build_definition.
"""

from pathlib import Path

from agent_spark_core import loop
from agent_def.config import build_definition

AGENT_SLUG = "cigna-mtsinai-negotiation"
AGENT_ROOT = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    loop.main(agent_slug=AGENT_SLUG, agent_root=AGENT_ROOT, build_definition=build_definition)
