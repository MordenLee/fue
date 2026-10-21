"""Validate packaged agent resources; never import executable configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Declaration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Limits(Declaration):
    max_model_calls: int = Field(ge=1, le=10)
    max_tool_calls: int = Field(ge=1, le=20)
    tool_timeout_seconds: int = Field(ge=1, le=120)
    run_timeout_seconds: int = Field(ge=1, le=600)
    max_tool_result_chars: int = Field(ge=100, le=100000)


class SkillRef(Declaration):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    activate_when: Literal["has_selected_knowledge_bases", "history_enabled", "has_readable_sources"]


class AgentDefinition(Declaration):
    schema_version: Literal[1]
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    version: str = Field(min_length=1)
    name: str = Field(min_length=1)
    prompt_file: str
    skills: list[SkillRef]
    allowed_tools: list[str]
    limits: Limits
    context_policy: Literal["conversation_budgeted"]
    output_policy: Literal["text_with_verified_references"]
    unsupported_tool_mode: Literal["retrieve_then_answer"]
    tool_protocol: Literal["evidence_synthesis", "native", "iterative_evidence"] = "evidence_synthesis"


class SkillDefinition(Declaration):
    schema_version: Literal[1]
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    version: str = Field(min_length=1)
    name: str = Field(min_length=1)
    instructions_file: str
    required_tools: list[str]
    required_resources: list[Literal["selected_knowledge_bases", "chat_history", "readable_sources"]]
    execution_policy: Literal["bounded_retrieval"]
    citation_policy: Literal["verified_evidence_only"]


@dataclass(frozen=True)
class ResolvedAgent:
    definition: AgentDefinition
    instructions: str
    skills: tuple[str, ...]
    tool_ids: frozenset[str]


class AgentRegistry:
    def __init__(self, root: Path, tool_ids: set[str]):
        self.root = root.resolve()
        self.agents: dict[str, AgentDefinition] = {}
        self.skills: dict[str, tuple[SkillDefinition, str]] = {}
        self.prompts: dict[str, str] = {}
        for path in sorted((self.root / "skills").glob("*/skill.json")):
            skill = SkillDefinition.model_validate_json(self._read(path))
            if skill.id != path.parent.name or skill.id in self.skills:
                raise ValueError(f"Invalid or duplicate skill ID: {skill.id}")
            if not set(skill.required_tools) <= tool_ids:
                raise ValueError(f"Unknown tools in skill {skill.id}")
            self.skills[skill.id] = (skill, self._reference(path.parent, skill.instructions_file))
        for path in sorted(self.root.glob("*.json")):
            agent = AgentDefinition.model_validate_json(self._read(path))
            if agent.id != path.stem or agent.id in self.agents:
                raise ValueError(f"Invalid or duplicate agent ID: {agent.id}")
            if not set(agent.allowed_tools) <= tool_ids:
                raise ValueError(f"Unknown tools in agent {agent.id}")
            refs = [ref.id for ref in agent.skills]
            if len(set(refs)) != len(refs):
                raise ValueError(f"Duplicate skill references in {agent.id}")
            for ref in agent.skills:
                if ref.id not in self.skills:
                    raise ValueError(f"Unknown skill: {ref.id}")
                if not set(self.skills[ref.id][0].required_tools) <= set(agent.allowed_tools):
                    raise ValueError(f"Skill tools exceed agent whitelist: {ref.id}")
            self.agents[agent.id] = agent
            self.prompts[agent.id] = self._reference(self.root, agent.prompt_file)
        if "chat" not in self.agents:
            raise ValueError("Missing built-in chat agent")

    def _read(self, path: Path) -> str:
        path = path.resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Agent resource path escapes packaged resource directory")
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            raise ValueError(f"Empty agent resource: {path.name}")
        return content

    def _reference(self, base: Path, reference: str) -> str:
        if Path(reference).is_absolute():
            raise ValueError("Agent resource references must be relative paths")
        return self._read(base / reference)

    def resolve(self, agent_id: str = "chat", *, has_knowledge_bases: bool = False, history_enabled: bool = False) -> ResolvedAgent:
        agent = self.agents[agent_id]
        instructions = [self.prompts[agent_id]]
        active, tools = [], set()
        for ref in agent.skills:
            conditions = {"has_selected_knowledge_bases": has_knowledge_bases, "history_enabled": history_enabled,
                          "has_readable_sources": has_knowledge_bases or history_enabled}
            if conditions[ref.activate_when]:
                skill, body = self.skills[ref.id]
                active.append(skill.id)
                tools.update(skill.required_tools)
                instructions.append(f"<skill id='{skill.id}'>\n{body}\n</skill>")
        return ResolvedAgent(agent, "\n\n".join(instructions), tuple(active), frozenset(tools))
