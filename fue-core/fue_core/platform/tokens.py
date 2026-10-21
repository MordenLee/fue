"""Existing mixed CJK/Latin budgeting estimates, shared without memory imports."""
import json


class ContextLimitError(ValueError):
    pass


def estimate(value):
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, default=str)
    return max(1, (len(value.encode("utf8")) + 2) // 3)


def estimate_messages(messages):
    return sum(estimate({"content": m.content, "tool_calls": getattr(m, "tool_calls", None),
                         "tool_call_id": getattr(m, "tool_call_id", None)}) + 8 for m in messages)
