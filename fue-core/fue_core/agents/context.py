"""Shared history and context checks for plain chat and tool-using agents."""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from fue_core.agents.registry import ResolvedAgent


from fue_core.platform.tokens import ContextLimitError


def build_context(agent: ResolvedAgent, messages, history_turns: int = 0):
    # A turn means a completed user/assistant pair; current question is additional.
    messages = list(messages)
    users = [i for i, m in enumerate(messages) if m.role == "user"]
    if history_turns > 0 and len(users) > history_turns + 1:
        split = users[-(history_turns + 1)]
        messages = [m for m in messages[:split] if m.role == "system"] + messages[split:]
    mapping = {"system": SystemMessage, "user": HumanMessage, "assistant": AIMessage}
    return [SystemMessage(content=agent.instructions)] + [
        mapping[m.role](content=m.content) for m in messages
    ]


def check_context(messages, context_length: int | None):
    if not context_length:
        return
    # Preserve existing mixed zh/en estimate, reserving 10% for output/overhead.
    estimated = sum(len(str(m.content)) for m in messages) // 2
    capacity = context_length * 1000
    if estimated > int(capacity * 0.9):
        raise ContextLimitError(
            f"Estimated token count ({estimated}) exceeds input budget for context "
            f"length ({capacity}). Shorten history or select a larger-context model."
        )
