"""Behavior tests for built-in resources, execution and the actual chat API routes.

Run from repository root: .venv/Scripts/python -m unittest discover -s backend/tests -v
No model credentials, application DB or Chroma collections are used.
"""

import asyncio
import json
import shutil
import sys
import unittest
from contextlib import contextmanager
from uuid import uuid4
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.tools import StructuredTool
from pydantic import ValidationError

from agents.context import ContextLimitError, build_context
from agents.registry import AgentRegistry
from agents.runner import AgentRunner
from agents.runtime import get_registry
from agents.tools import SearchArguments, ReadArguments, ToolBinding, make_knowledge_binding, TOOL_IDS
from chat import router as api


RESOURCES = Path(__file__).resolve().parents[1] / "agents" / "resources"
TEST_TEMP_ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def scratch_directory():
    # Python 3.14's TemporaryDirectory applies a private Windows ACL that blocks
    # the managed sandbox token. Inherit the writable workspace ACL instead.
    root = TEST_TEMP_ROOT / f".tmp_agent_{uuid4().hex}"
    root.mkdir()
    try:
        yield str(root)
    finally:
        resolved = root.resolve()
        if not resolved.is_relative_to(TEST_TEMP_ROOT) or not resolved.name.startswith(".tmp_agent_"):
            raise ValueError("Unexpected test cleanup path")
        shutil.rmtree(resolved)


class FakeModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.inputs = []
        self.bindings = []

    def bind_tools(self, tools):
        self.bindings.append(tools)
        return self

    async def ainvoke(self, messages):
        self.inputs.append(messages)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def astream(self, messages):
        response = await self.ainvoke(messages)
        yield AIMessageChunk(content=response.content, tool_calls=response.tool_calls)


def binding(execute=None):
    execute = execute or AsyncMock(return_value="[CITE-1] Verified excerpt")
    tool = StructuredTool.from_function(
        name="search_knowledge_base", description="Search documents", args_schema=SearchArguments,
        coroutine=execute,
    )
    return ToolBinding("knowledge.search", tool, execute)


def tool_response(name="search_knowledge_base", query="topic"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": {"query": query}, "id": "call-1"}])


class RegistryTests(unittest.TestCase):
    def test_scope_determines_active_skill_and_tools(self):
        registry = get_registry()
        plain = registry.resolve()
        rag = registry.resolve(has_knowledge_bases=True)
        self.assertEqual(plain.skills, ())
        self.assertEqual(plain.tool_ids, frozenset())
        self.assertEqual(rag.skills, ("knowledge-qa", "context-reading"))
        self.assertEqual(rag.tool_ids, frozenset({"knowledge.search", "sources.read"}))
        self.assertNotIn("<skill", plain.instructions)
        self.assertIn("knowledge-qa", rag.instructions)

    def test_resource_edit_reaches_model_context_without_python_change(self):
        with scratch_directory() as root:
            shutil.copytree(RESOURCES, root, dirs_exist_ok=True)
            skill = Path(root) / "skills/knowledge-qa/SKILL.md"
            skill.write_text("Unique changed skill instruction", encoding="utf-8")
            agent = AgentRegistry(Path(root), TOOL_IDS).resolve(has_knowledge_bases=True)
            messages = build_context(agent, [api.ChatMessage(role="user", content="hello")])
            self.assertIn("Unique changed skill instruction", messages[0].content)

    def test_bad_fields_and_unknown_tools_fail(self):
        for changes in ({"unexpected": True}, {"allowed_tools": ["shell.execute"]}):
            with self.subTest(changes=changes), scratch_directory() as root:
                shutil.copytree(RESOURCES, root, dirs_exist_ok=True)
                file = Path(root) / "chat.json"
                data = json.loads(file.read_text(encoding="utf-8"))
                file.write_text(json.dumps({**data, **changes}), encoding="utf-8")
                with self.assertRaises((ValueError, ValidationError)):
                    AgentRegistry(Path(root), TOOL_IDS)

    def test_prompt_path_escape_fails(self):
        with scratch_directory() as parent:
            root = Path(parent) / "resources"
            shutil.copytree(RESOURCES, root)
            outside = Path(parent) / "outside.md"
            outside.write_text("outside", encoding="utf-8")
            file = root / "chat.json"
            data = json.loads(file.read_text(encoding="utf-8"))
            data["prompt_file"] = "../outside.md"
            file.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "escapes"):
                AgentRegistry(root, TOOL_IDS)

    def test_history_keeps_completed_turn_and_current_question(self):
        messages = [api.ChatMessage(role=role, content=f"{i}-{role}")
                    for i in range(3) for role in ("user", "assistant")]
        messages.append(api.ChatMessage(role="user", content="current"))
        for rag in (False, True):
            agent = get_registry().resolve(has_knowledge_bases=rag)
            context = build_context(agent, messages, history_turns=1)
            self.assertEqual([m.content for m in context[1:]], ["2-user", "2-assistant", "current"])


def search_agent():
    agent = get_registry().resolve(has_knowledge_bases=True)
    return replace(agent, tool_ids=frozenset({"knowledge.search"}))


class RunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_knowledge_adapter_owns_session_and_binds_resource_scope(self):
        factory = MagicMock()
        local_db = factory.return_value.__enter__.return_value
        from chat.tools import RetrievedChunk
        chunk = RetrievedChunk("[CITE-8]", 1, 0, "test.txt", 3, "source", 0.1)
        search = MagicMock()
        search.invoke.return_value = "[CITE-8] source"
        retrieved = []
        with patch("chat.tools.make_search_tool", return_value=(search, [chunk])) as create:
            tool = make_knowledge_binding([3, 7], retrieved, factory, initial_cite_num=8)
            result = await tool.execute({"query": "topic"})
        create.assert_called_once_with([3, 7], local_db, 8, raise_on_error=True)
        factory.return_value.__exit__.assert_called_once()
        self.assertEqual(retrieved, [chunk])
        self.assertEqual(result.status, "ok")
        with self.assertRaises(ValidationError):
            await tool.execute({"query": "x", "unregistered_argument": [999]})

    async def test_plain_streaming_and_nonstreaming_agree(self):
        for streaming in (False, True):
            model = FakeModel([AIMessage(content="你好\nsecond line")])
            agent = get_registry().resolve()
            events = [e async for e in AgentRunner(agent, model).events(
                build_context(agent, [api.ChatMessage(role="user", content="hi")]), streaming=streaming)]
            self.assertEqual(events[-1].data, "你好\nsecond line")
            self.assertFalse(model.bindings)

    async def test_actual_tool_loop_uses_skill_and_evidence_in_both_modes(self):
        for streaming in (False, True):
            model = FakeModel([tool_response(), AIMessage(content="Answer [CITE-1]")])
            tool = binding()
            agent = search_agent()
            events = [e async for e in AgentRunner(agent, model, [tool]).events(
                build_context(agent, [api.ChatMessage(role="user", content="topic")]), streaming=streaming)]
            tool.execute.assert_awaited_once_with({"query": "topic", "mode": "vector", "top_n": 0, "kb_ids": None})
            self.assertIn("知识库问答", model.inputs[0][0].content)
            self.assertIn("Verified excerpt", model.inputs[1][-1].content)
            self.assertEqual(events[-1].data, "Answer [CITE-1]")

    async def test_unregistered_model_tool_is_never_executed(self):
        tool = binding()
        agent = search_agent()
        runner = AgentRunner(agent, FakeModel([tool_response("shell")]), [tool])
        with self.assertRaisesRegex(ValueError, "unregistered"):
            _ = [e async for e in runner.events(build_context(agent, [api.ChatMessage(role="user", content="hi")]), streaming=False)]
        tool.execute.assert_not_awaited()

    async def test_tool_error_is_data_and_final_answer_can_explain_failure(self):
        agent = search_agent()
        tool = binding(AsyncMock(side_effect=RuntimeError("backend unavailable")))
        model = FakeModel([tool_response(), AIMessage(content="检索失败")])
        events = [e async for e in AgentRunner(agent, model, [tool]).events(
            build_context(agent, [api.ChatMessage(role="user", content="hi")]), streaming=False)]
        self.assertIn('"status": "error"', model.inputs[-1][-1].content)
        self.assertEqual(events[-1].data, "检索失败")

    async def test_native_loop_caps_model_calls_and_reuses_tool_result(self):
        base = search_agent()
        agent = replace(base, definition=base.definition.model_copy(update={"tool_protocol": "native"}))
        tool = binding()
        model = FakeModel([tool_response(), tool_response(), AIMessage(content="done")])
        _ = [e async for e in AgentRunner(agent, model, [tool]).events(
            build_context(agent, [api.ChatMessage(role="user", content="hi")]), streaming=False)]
        tool.execute.assert_awaited_once()
        self.assertEqual(len(model.inputs), 3)

    async def test_context_checked_again_after_tool_result(self):
        agent = search_agent()
        tool = binding(AsyncMock(return_value="x" * 20000))
        model = FakeModel([tool_response(), AIMessage(content="bounded answer")])
        events = [e async for e in AgentRunner(agent, model, [tool], context_length=8).events(
            build_context(agent, [api.ChatMessage(role="user", content="hi")]), streaming=False)]
        self.assertEqual(events[-1].data, "bounded answer")
        self.assertLess(sum(len(str(m.content)) for m in model.inputs[-1]), 9000)

    async def test_cancellation_does_not_run_following_model_call(self):
        started = asyncio.Event()
        async def wait(args):
            started.set()
            await asyncio.Event().wait()
        agent = search_agent()
        model = FakeModel([tool_response(), AIMessage(content="late")])
        async def consume():
            return [e async for e in AgentRunner(agent, model, [binding(wait)]).events(
                build_context(agent, [api.ChatMessage(role="user", content="hi")]), streaming=False)]
        task = asyncio.create_task(consume())
        await asyncio.wait_for(started.wait(), timeout=5)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(len(model.inputs), 1)

    async def test_declared_binding_fallback_retrieves_before_answer(self):
        model = FakeModel([AIMessage(content="answer")])
        model.bind_tools = MagicMock(side_effect=NotImplementedError())
        agent = search_agent()
        tool = binding()
        _ = [e async for e in AgentRunner(agent, model, [tool]).events(
            build_context(agent, [api.ChatMessage(role="user", content="question")]), streaming=False)]
        tool.execute.assert_awaited_once_with({"query": "question", "mode": "vector", "top_n": 0, "kb_ids": None})
        self.assertIn("Verified excerpt", model.inputs[0][-1].content)

    async def test_invalid_tool_arguments_never_reach_implementation(self):
        agent = search_agent()
        tool = binding()
        response = AIMessage(content="", tool_calls=[{
            "name": "search_knowledge_base", "args": {"query": "x", "unregistered_argument": [999]}, "id": "bad"}])
        model = FakeModel([response, AIMessage(content="invalid arguments")])
        _ = [e async for e in AgentRunner(agent, model, [tool]).events(
            build_context(agent, [api.ChatMessage(role="user", content="hi")]), streaming=False)]
        tool.execute.assert_not_awaited()
        self.assertIn('"status": "error"', model.inputs[-1][-1].content)

    async def test_execution_budget_forces_last_call_without_tools(self):
        base = search_agent()
        definition = base.definition.model_copy(update={
            "tool_protocol": "native", "limits": base.definition.limits.model_copy(update={"max_model_calls": 2})})
        agent = replace(base, definition=definition)
        model = FakeModel([tool_response(), tool_response()])
        with self.assertRaisesRegex(ValueError, "disabled"):
            _ = [e async for e in AgentRunner(agent, model, [binding()]).events(
                build_context(agent, [api.ChatMessage(role="user", content="hi")]), streaming=False)]
        self.assertEqual(len(model.inputs), 2)

    async def test_total_retrieval_budget_is_shared_and_reserves_final_answer(self):
        base = search_agent()
        agent = replace(base, definition=base.definition.model_copy(update={
            "limits": base.definition.limits.model_copy(update={"max_tool_result_chars": 2000})}))
        tool = binding(AsyncMock(return_value='"large evidence" ' * 2000))
        model = FakeModel([tool_response(), AIMessage(content="bounded final answer")])
        events = [e async for e in AgentRunner(agent, model, [tool]).events(
            build_context(agent, [api.ChatMessage(role="user", content="hi")]), streaming=False)]
        self.assertEqual(events[-1].data, "bounded final answer")
        block = model.inputs[-1][-1].content
        self.assertLessEqual(len(block), 2100)
        self.assertIn('"truncated": true', block)
        tool.execute.assert_awaited_once()

    async def test_search_catalog_cannot_consume_reserved_reading_budget(self):
        base = search_agent()
        agent = replace(base, tool_ids=frozenset({"knowledge.search", "sources.read"}))
        search = binding(AsyncMock(return_value="catalog " * 10000))
        read_execute = AsyncMock(return_value="actual adjacent context")
        read = ToolBinding("sources.read", StructuredTool.from_function(
            name="read_context", description="Read context", args_schema=ReadArguments, coroutine=read_execute), read_execute)
        read_call = AIMessage(content="", tool_calls=[{"name": "read_context", "id": "read-1",
                                                      "args": {"source": "chat", "pair_id": "test"}}])
        model = FakeModel([tool_response(), read_call, AIMessage(content="read complete")])
        events = [e async for e in AgentRunner(agent, model, [search, read]).events(
            build_context(agent, [api.ChatMessage(role="user", content="hi")]), streaming=False)]
        self.assertEqual(events[-1].data, "read complete")
        read_execute.assert_awaited_once()
        self.assertEqual([t.name for t in model.bindings[-1]], ["read_context"])
        self.assertIn('"name": "read_context", "status": "ok"', model.inputs[-1][-1].content)

    async def test_duplicate_search_is_cached_then_reader_remains_available(self):
        base = search_agent()
        agent = replace(base, tool_ids=frozenset({"knowledge.search", "sources.read"}))
        search = binding()
        execute = AsyncMock(return_value="neighbor context")
        reader = ToolBinding("sources.read", StructuredTool.from_function(
            name="read_context", description="Read", args_schema=ReadArguments, coroutine=execute), execute)
        read_call = AIMessage(content="", tool_calls=[{"name": "read_context", "id": "read-1",
                                                      "args": {"source": "chat", "pair_id": "test"}}])
        model = FakeModel([tool_response(), tool_response(), read_call, AIMessage(content="done")])
        _ = [e async for e in AgentRunner(agent, model, [search, reader]).events(
            build_context(agent, [api.ChatMessage(role="user", content="hi")]), streaming=False)]
        search.execute.assert_awaited_once()
        execute.assert_awaited_once()
        self.assertEqual([t.name for t in model.bindings[-1]], ["read_context"])
        self.assertTrue(model.inputs[-1][-1].content.startswith("<execution-receipts>"))


class RouteTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.model = SimpleNamespace(qps=0, context_length=64, display_name="test", provider=SimpleNamespace(name="fake"))
        self.db = MagicMock()
        self.db.get.side_effect = lambda cls, key: None if cls is api.Setting else SimpleNamespace(id=key)
        self.patches = [patch.object(api, "_get_chat_model", return_value=self.model)]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    async def test_all_four_routes_reach_shared_runner(self):
        for rag in (False, True):
            for streaming in (False, True):
                with self.subTest(rag=rag, streaming=streaming):
                    model = FakeModel(([tool_response()] if rag else []) + [AIMessage(content="line1\nline2")])
                    payload = (api.RAGChatRequest(kb_ids=[7], conversation_id=4,
                               messages=[api.ChatMessage(role="user", content="hi")]) if rag else
                               api.ChatRequest(conversation_id=4, messages=[api.ChatMessage(role="user", content="hi")]))
                    tool = binding()
                    with patch.object(api, "build_llm", return_value=model), \
                         patch.object(api, "make_knowledge_binding", return_value=tool), \
                         patch.object(api, "_save_turn") as save, \
                         patch.object(api, "build_rag_response", side_effect=lambda text, *a, **kw: (text, [], {})):
                        route = (api.chat_rag_stream if streaming else api.chat_rag) if rag else (api.chat_stream if streaming else api.chat)
                        response = await route(1, payload, self.db)
                        if streaming:
                            body = "".join([item async for item in response.body_iterator])
                            self.assertIn('[REPLACE] "line1\\nline2"', body)
                            self.assertIn("[DONE]", body)
                            self.assertNotIn("[ERROR]", body)
                        else:
                            self.assertEqual(response.content, "line1\nline2")
                        self.assertIn("FUE", model.inputs[0][0].content)
                        self.assertEqual(bool(model.bindings), rag)
                        save.assert_called_once()
                        self.assertEqual(save.call_args.args[3], "line1\nline2")

    async def test_failed_persistence_emits_error_instead_of_successful_replace(self):
        model = FakeModel([AIMessage(content="answer")])
        payload = api.ChatRequest(conversation_id=4, messages=[api.ChatMessage(role="user", content="hi")])
        with patch.object(api, "build_llm", return_value=model), \
             patch.object(api, "_save_turn", side_effect=RuntimeError("disk full")), \
             self.assertLogs(api.logger, level="ERROR"):
            response = await api.chat_stream(1, payload, self.db)
            body = "".join([item async for item in response.body_iterator])
        self.assertIn("[ERROR] disk full", body)
        self.assertNotIn("[REPLACE]", body)
        self.db.rollback.assert_called_once()

    async def test_unset_request_cap_does_not_silently_limit_setting_to_five(self):
        self.db.get.side_effect = lambda cls, key: (
            SimpleNamespace(value="12") if cls is api.Setting and key == "chat_max_tool_rounds" else None)
        payload = api.RAGChatRequest(kb_ids=[7], messages=[api.ChatMessage(role="user", content="hi")])
        self.db.get.side_effect = lambda cls, key: (
            SimpleNamespace(value="12") if cls is api.Setting and key == "chat_max_tool_rounds" else
            None if cls is api.Setting else SimpleNamespace(id=key))
        with patch.object(api, "build_llm", return_value=FakeModel([])):
            _, runner, _, _ = api._prepare(1, payload, self.db, rag=True)
        self.assertEqual(runner.tool_budget, 12)


class HttpIntegrationTests(unittest.TestCase):
    """Real API serialization, ORM storage and citation finalization with a fake LLM."""

    def test_http_routes_persist_the_same_final_answer_the_client_receives(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        from database import Base
        from providers.models import AIModel, Provider
        from knowledge.models import KnowledgeBase
        from knowledge.documents.models import DocumentFile
        from chat.tools import RetrievedChunk

        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        sessions = sessionmaker(bind=engine)
        Base.metadata.create_all(engine)
        with sessions() as db:
            provider = Provider(name="fake", interface_type="openai")
            db.add(provider)
            db.flush()
            model = AIModel(provider_id=provider.id, api_name="fake", display_name="Fake", context_length=64)
            db.add(model)
            db.flush()
            kb = KnowledgeBase(name="test", embed_model_id=model.id)
            db.add(kb)
            db.flush()
            doc = DocumentFile(knowledge_base_id=kb.id, original_filename="source.txt",
                               file_path="source.txt", file_type="txt", file_size=20)
            db.add(doc)
            db.flush()
            model_id, kb_id, doc_id = model.id, kb.id, doc.id
            db.commit()

        app = FastAPI()
        app.include_router(api.router)
        def database():
            with sessions() as db:
                yield db
        app.dependency_overrides[api.get_db] = database

        def knowledge_binding(kb_ids, retrieved, session_factory, initial):
            self.assertEqual(kb_ids, [kb_id])
            async def execute(args):
                retrieved.append(RetrievedChunk(f"[CITE-{initial}]", doc_id, 0, "source.txt", kb_id, "Verified evidence", 0.1))
                return f"[CITE-{initial}] Verified evidence"
            return binding(execute)

        try:
            with TestClient(app) as client:
                for rag in (False, True):
                    for streaming in (False, True):
                        with self.subTest(rag=rag, streaming=streaming):
                            with sessions() as db:
                                conv = api.Conversation(title="test")
                                db.add(conv)
                                db.commit()
                                conv_id = conv.id
                            model = FakeModel(([tool_response()] if rag else []) + [AIMessage(content="Answer\nline2 [CITE-1]" if rag else "Answer\nline2")])
                            body = {"conversation_id": conv_id, "messages": [{"role": "user", "content": "question"}]}
                            if rag:
                                body["kb_ids"] = [kb_id]
                            endpoint = f"/api/chat/{model_id}" + ("/rag" if rag else "") + ("/stream" if streaming else "")
                            with patch.object(api, "build_llm", return_value=model), \
                                 patch.object(api, "make_knowledge_binding", side_effect=knowledge_binding):
                                response = client.post(endpoint, json=body)
                            self.assertEqual(response.status_code, 200, response.text)
                            expected = "Answer\nline2 [1]" if rag else "Answer\nline2"
                            if streaming:
                                self.assertNotIn("[ERROR]", response.text)
                                self.assertIn("[REPLACE] " + json.dumps(expected), response.text)
                            else:
                                self.assertEqual(response.json()["content"], expected)
                                if rag:
                                    self.assertEqual(response.json()["references"][0]["chunks"][0]["chunk_content"], "Verified evidence")
                            with sessions() as db:
                                rows = db.query(api.Message).filter_by(conversation_id=conv_id).order_by(api.Message.position).all()
                                self.assertEqual([r.role for r in rows], ["user", "assistant"])
                                self.assertEqual(rows[-1].content, expected)
                                if rag:
                                    self.assertEqual(rows[-1].references[0]["document_file_id"], doc_id)
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
