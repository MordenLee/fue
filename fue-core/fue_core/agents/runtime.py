"""Application-owned built-ins, loaded once and validated before serving requests."""

from functools import lru_cache
from pathlib import Path

from fue_core.agents.registry import AgentRegistry
from fue_core.agents.tools import TOOL_IDS


@lru_cache(maxsize=1)
def get_registry() -> AgentRegistry:
    return AgentRegistry(Path(__file__).parent / "resources", TOOL_IDS)
