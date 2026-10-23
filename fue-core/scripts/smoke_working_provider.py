"""Opt-in paid smoke test: real configured model, synthetic QA, isolated SQLite.

No user conversations, knowledge documents or embedding requests are used.
"""
import argparse
import asyncio
import json
import logging
import re
import shutil
import sys
import time
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine
from sqlalchemy.orm import joinedload, sessionmaker
from sqlalchemy.pool import StaticPool
from fue_core.database import Base, SessionLocal
from fue_core.providers.models import AIModel, Provider
from fue_core.conversations.models import Conversation, MessageAppend, MessageCreate, Message
from fue_core.conversations.router import append_messages
from fue_core.settings.models import Setting
from fue_core.memory.models import ContextSummary, ContextEvent, ModelUsage, QAPair
from fue_core.memory import working
from fue_core.agents.runtime import get_registry
from fue_core.agents.usage import UsageLedger
from fue_core.chat import service as api
from fue_core.chat.router import router as _registered_chat_router
from fue_core import knowledge


async def main(args):
    logging.disable(logging.CRITICAL)
    with SessionLocal() as db:
        model = db.query(AIModel).options(joinedload(AIModel.provider)).filter_by(id=args.model_id).one()
        if not model.is_enabled or not model.provider.is_enabled or not model.provider.api_key:
            raise ValueError("Select an enabled configured chat model")
        model_data = {c.name: getattr(model, c.name) for c in AIModel.__table__.columns}
        provider_data = {c.name: getattr(model.provider, c.name) for c in Provider.__table__.columns}
        secrets = [p.api_key for p in db.query(Provider).all() if p.api_key]
    scratch = Path(__file__).resolve().parents[2] / (".tmp_live_working_" + uuid4().hex)
    scratch.mkdir()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    report = {"passed": False, "model": model_data["api_name"], "synthetic_only": True, "prepare_only": args.prepare_only}
    started = time.monotonic()
    try:
        with sessions() as db:
            db.add(Provider(**provider_data)); db.add(AIModel(**model_data))
            for key, value in {"memory_query_scope": "all", "memory_query_mode": "keyword",
                               "chat_context_mode": "working", "chat_input_tokens": "8000",
                               "chat_output_tokens": "1536", "chat_run_input_tokens": "24000",
                               "chat_run_output_tokens": "6144", "chat_summary_chars": "1400",
                               "chat_summary_tokens": "1100", "chat_max_tool_rounds": "2",
                               "chat_compress_model_id": str(args.model_id)}.items():
                db.add(Setting(key=key, value=value))
            conv = Conversation(title="Synthetic working-memory validation")
            db.add(conv); db.commit(); cid = conv.id
            for i in range(8):
                question = ("筛选标准：只纳入2020年及以后的中国制造业企业实证研究；排除综述；最多纳入8篇。" if i == 0 else f"材料{i}已判断，继续保持原筛选标准。")
                answer = (("This synthetic material has already been evaluated. " * 35) +
                          ("\n原始批次校验码：MANGO-4827。" if i == 0 else "\n材料暂未采用。"))
                append_messages(cid, MessageAppend(messages=[MessageCreate(role="user", content=question),
                                                            MessageCreate(role="assistant", content=answer)]), db)
            pair = db.query(QAPair).filter_by(state="complete").order_by(QAPair.position).first()
            ref = "chat:"+pair.id
        tools, successes, activities, answer, errors = [], [], [], None, []
        question = (f"这是人工记忆验证。先调用 read_memory 读取 {ref}，offset=0，length=4000；不要搜索。"
                    "再报告原始批次校验码以及仍有效的筛选年份下限、研究对象、排除条件和篇数上限。"
                    "不要编造缺失细节，答案不超过180字。")
        original_render = working.render
        def inspect_draft(items):
            body = original_render(items)
            report["candidate_chars"] = len(body)
            report["candidate_items"] = len(items)
            return body
        with patch.object(api, "SessionLocal", sessions), patch.object(working, "data_dir", return_value=scratch), patch.object(working, "render", side_effect=inspect_draft):
            if args.prepare_only:
                with sessions() as db:
                    append_messages(cid, MessageAppend(messages=[MessageCreate(role="user", content=question)]), db)
                ledger = UsageLedger(per_input=8000, per_output=1536, input_limit=24000, output_limit=6144,
                    sink=lambda category, mid, info: working.save_usage(sessions, cid, "prepare-check", category, mid, info))
                async for item in working.prepare(sessions, cid, get_registry().resolve(history_enabled=True),
                                                 model_data["context_length"], [], "prepare-check", ledger):
                    if item["type"] != "_messages":
                        activities.append(item)
                        print("EVENT " + json.dumps(item, ensure_ascii=True), flush=True)
            else:
                with sessions() as db:
                    response = await api.chat_stream(args.model_id, api.ChatRequest(conversation_id=cid,
                               messages=[api.ChatMessage(role="user", content=question)]), db)
                    async for frame in response.body_iterator:
                        if frame.startswith("data: [ACTIVITY] "):
                            item = json.loads(frame[len("data: [ACTIVITY] "):].strip())
                            activities.append(item)
                            if item["type"] != "waiting":
                                print("EVENT " + json.dumps(item, ensure_ascii=True), flush=True)
                            if item["type"] == "tool_completed" and item["status"] == "ok":
                                successes.append(item["name"])
                        elif frame.startswith("data: [TOOL_CALL] "):
                            tools.append(json.loads(frame[len("data: [TOOL_CALL] "):].strip()))
                        elif frame.startswith("data: [REPLACE] "):
                            answer = json.loads(frame[len("data: [REPLACE] "):].strip())
                        elif frame.startswith("data: [ERROR] "):
                            errors.append(frame[len("data: [ERROR] "):].strip())
            with sessions() as db:
                head = db.query(ContextSummary).filter_by(active=True).first()
                summary_text = "\n".join(item["text"] for item in head.items) if head else ""
                summary_ok = bool(head and "2020" in summary_text and re.search(r"8\s*篇|\b8\b", summary_text) and
                                  working.summary_path(db, cid).exists() and len(head.markdown) <= 1400)
                report["summary_chars"] = len(head.markdown) if head else None
                report["summary"] = summary_text
                report["usage"] = [{"category": u.category, "status": u.status, "input_estimated": u.input_estimated,
                                    "output_estimated": u.output_estimated, "usage": u.usage, "elapsed_ms": u.elapsed_ms}
                                   for u in db.query(ModelUsage).all()]
            # Prove a follow-up can reuse the summary without another paid request.
            reuse_ok = False
            if summary_ok and (args.prepare_only or answer) and not errors:
                if not args.prepare_only:
                    with sessions() as db:
                        append_messages(cid, MessageAppend(messages=[MessageCreate(role="user", content="继续，保持已有标准。")]), db)
                class NoPaidRecall(UsageLedger):
                    async def invoke(self, *a, **kw):
                        raise AssertionError("Unexpected paid call while reusing summary")
                reused = [e async for e in working.prepare(sessions, cid, get_registry().resolve(history_enabled=True),
                          model_data["context_length"], [], "reuse-check", NoPaidRecall())]
                reuse_ok = not any(e["type"] == "compaction_started" for e in reused)
            report.update({"summary_ok": summary_ok, "reuse_without_model_call": reuse_ok,
                           "tools": [t["name"] for t in tools], "successful_tools": successes,
                           "answer": answer, "errors": errors})
            report["passed"] = bool(summary_ok and reuse_ok and answer and "MANGO-4827" in answer and
                                    "2020" in answer and re.search(r"8\s*篇|\b8\b", answer) and
                                    "制造业" in answer and "综述" in answer and "read_memory" in successes and not errors)
            if args.prepare_only:
                report["passed"] = bool(summary_ok and reuse_ok and not errors)
    except Exception as exc:
        report["failure"] = type(exc).__name__ + ": " + str(exc)
    finally:
        report["elapsed_seconds"] = round(time.monotonic()-started, 2)
        engine.dispose()
        if scratch.resolve().is_relative_to(Path(__file__).resolve().parents[2]) and scratch.name.startswith(".tmp_live_working_"):
            shutil.rmtree(scratch)
    output = json.dumps(report, ensure_ascii=False, indent=2)
    for secret in secrets:
        output = output.replace(secret, "[REDACTED]")
    if args.report:
        Path(args.report).write_text(output+"\n", encoding="utf8")
    print(output.encode("ascii", "backslashreplace").decode(), flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", type=int, default=32)
    parser.add_argument("--report")
    parser.add_argument("--prepare-only", action="store_true", help="One summary request only; no paid main-model answer")
    raise SystemExit(asyncio.run(main(parser.parse_args())))
