"""Application-owned built-ins, loaded once and validated before serving requests."""

from functools import lru_cache
from pathlib import Path

from agents.registry import AgentRegistry
from agents.tools import TOOL_IDS


@lru_cache(maxsize=1)
def get_registry() -> AgentRegistry:
    return AgentRegistry(Path(__file__).parent / "resources", TOOL_IDS)
