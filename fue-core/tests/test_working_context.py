"""Real SQLite / file projection tests. Never load user data or paid providers."""
import asyncio
import json
import shutil
import sys
import time
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import FastAPI
from fastapi.testclient import TestClient
from database import Base, get_db
from providers.models import Provider, AIModel
from conversations.models import Conversation, Message, MessageAppend, MessageCreate
from conversations import router as conversations
from settings.models import Setting
from memory.models import QAPair, ContextSummary, ContextEvent, ModelUsage
from memory import service, working
from memory.workspace import update_material, MaterialUpdate, router as workspace_router
from agents.runtime import get_registry
from agents.usage import UsageLedger
from agents.context import ContextLimitError
from chat import router as chat


class ProviderFixture:
    def __init__(self, *, oversize=False, during=None):
        self.calls = []
        self.caps = []
        self.oversize, self.during = oversize, during

    def bind(self, **kw):
        self.caps.append(kw)
        return self

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.calls.append(messages)
        if "只输出 JSON" in messages[0].content:
            payload = json.loads(messages[-1].content)
            if self.during:
                self.during()
            body = json.dumps({"items": [{"section": 1, "text": "用户要求保留标准 ORIGINAL-CRITERION" + ("x"*1400 if self.oversize else ""),
                                          "sources": [payload["new_pairs"][0]["id"]]}]}, ensure_ascii=False)
        else:
            body = "final answer"
        return AIMessage(content=body, usage_metadata={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150})

    async def astream(self, messages):
        response = await self.ainvoke(messages)
        yield AIMessageChunk(content=response.content, usage_metadata=response.usage_metadata)


class WorkingContextTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[2] / (".tmp_working_"+uuid4().hex)
        self.root.mkdir()
        self.engine = create_engine("sqlite:///"+str(self.root/"app.db"), connect_args={"check_same_thread": False})
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        with self.factory() as db:
            provider = Provider(name="isolated", interface_type="openai")
            db.add(provider); db.flush()
            model = AIModel(provider_id=provider.id, api_name="fake", display_name="Fake", context_length=64)
            db.add(model); db.flush(); self.model_id = model.id
            conv = Conversation(title="isolated")
            db.add(conv); db.flush(); self.cid = conv.id
            for key, value in {"memory_query_scope":"all", "chat_context_mode":"working", "chat_input_tokens":"4096",
                               "chat_output_tokens":"512", "chat_summary_chars":"1200", "chat_compress_model_id":str(model.id)}.items():
                db.add(Setting(key=key, value=value))
            db.commit()
        fake_chroma = MagicMock()
        fake_chroma.list_collections.return_value = []
        p = patch("knowledge.chroma.get_chroma_client", return_value=fake_chroma)
        p.start(); self.addCleanup(p.stop)

    def tearDown(self):
        self.engine.dispose()
        assert self.root.resolve().is_relative_to(Path(__file__).resolve().parents[2]) and self.root.name.startswith('.tmp_working_')
        shutil.rmtree(self.root)

    def put_setting(self, key, value):
        with self.factory() as db:
            db.merge(Setting(key=key, value=value)); db.commit()

    def history(self, n=8, size=1000):
        with self.factory() as db:
            for i in range(n):
                conversations.append_messages(self.cid, MessageAppend(messages=[
                    MessageCreate(role="user", content=f"ORIGINAL-CRITERION {i} "+"x"*size),
                    MessageCreate(role="assistant", content="processed "+"y"*size)]), db)
            conversations.append_messages(self.cid, MessageAppend(messages=[MessageCreate(role="user", content="continue")]), db)

    async def plan(self, fixture=None, ledger=None):
        fixture = fixture or ProviderFixture()
        ledger = ledger or UsageLedger()
        with patch("providers.chat.build_llm", return_value=fixture):
            return [e async for e in working.prepare(self.factory, self.cid, get_registry().resolve(history_enabled=True), 64, [], "test-run", ledger)]

    async def test_compaction_persists_md_event_and_reuses_summary_without_model_call(self):
        self.history()
        fixture = ProviderFixture()
        events = await self.plan(fixture)
        self.assertIn('compaction_completed', [e['type'] for e in events])
        self.assertEqual(len(fixture.calls), 1)
        payload = json.loads(fixture.calls[0][-1].content)
        self.assertEqual([m['role'] for m in payload['new_pairs'][0]['messages']], ['user', 'assistant'])
        with self.factory() as db:
            head = db.query(ContextSummary).filter_by(active=True).one()
            self.assertLessEqual(len(head.markdown), 1200)
            self.assertIn('ORIGINAL-CRITERION', working.summary_path(db, self.cid).read_text(encoding='utf8'))
            self.assertEqual(db.query(Message).count(), 17)
            entry = db.query(ContextEvent).filter_by(type='compaction_completed').one()
            directory = working.read_memory(db, 'compaction:'+entry.id, length=4000)
            pair_id = entry.payload['dependencies'][0]['id']
            self.assertIn(pair_id, directory['text'])
            self.assertIn('ORIGINAL-CRITERION', working.read_memory(db, 'chat:'+pair_id)['text'])
        again = ProviderFixture()
        updates = await self.plan(again)
        self.assertEqual(again.calls, [])
        self.assertIn('compaction:', updates[-1]['messages'][1].content + updates[-1]['messages'][2].content)

    async def test_completed_material_pruned_locally_and_can_be_restored(self):
        self.history(1, 6000)
        with self.factory() as db:
            pair = db.query(QAPair).filter_by(state='complete').one()
            update_material(self.cid, MaterialUpdate(pair_id=pair.id, status='completed', decision='not_selected', result='用户标准不符，保留判定'), db)
            ref = db.query(working.ConversationMaterial).one().id
        fixture = ProviderFixture()
        updates = await self.plan(fixture)
        content = '\n'.join(str(m.content) for m in updates[-1]['messages'])
        self.assertNotIn('x'*100, content)
        self.assertIn('用户标准不符', content)
        self.assertEqual(fixture.calls, [])
        with self.factory() as db:
            self.assertIn('x'*100, working.read_memory(db, 'material:'+ref, length=4000)['text'])
            update_material(self.cid, MaterialUpdate(pair_id=pair.id, status='pending'), db)
        with self.assertRaises(ContextLimitError):
            await self.plan()

    async def test_disabled_and_time_scope_apply_to_direct_ids(self):
        self.history(1, 100)
        with self.factory() as db:
            pair = db.query(QAPair).filter_by(state='complete').one()
            pair.timestamp = int(time.time())-10*86400; db.commit(); pair_id = pair.id
        self.put_setting('memory_query_scope','7')
        with self.factory() as db, self.assertRaises(PermissionError):
            working.read_memory(db, 'chat:'+pair_id)
        self.put_setting('memory_query_scope','disabled')
        with self.factory() as db, self.assertRaises(PermissionError):
            working.read_memory(db, 'chat:'+pair_id)

    async def test_invalid_summary_does_not_commit_or_retry(self):
        self.history()
        fixture = ProviderFixture(oversize=True)
        with self.assertRaises(ContextLimitError):
            await self.plan(fixture)
        self.assertEqual(len(fixture.calls),1)
        with self.factory() as db:
            self.assertEqual(db.query(ContextSummary).count(),0)
            self.assertEqual(db.query(ContextEvent).filter_by(type='compaction_failed').count(),1)
            self.assertEqual(db.query(Message).count(),17)

    async def test_edit_during_summary_rejects_late_candidate(self):
        self.history()
        def change():
            with self.factory() as db:
                msg = db.query(Message).order_by(Message.id).first()
                conversations.update_message(self.cid,msg.id,{'content':'changed criteria'},db)
        with self.assertRaises(ContextLimitError):
            await self.plan(ProviderFixture(during=change))
        with self.factory() as db:
            self.assertEqual(db.query(ContextSummary).filter_by(active=True).count(),0)

    async def test_delete_purges_summary_file_and_all_derived_records(self):
        self.history()
        await self.plan()
        with self.factory() as db:
            path = working.summary_path(db,self.cid)
            self.assertTrue(path.exists())
            msg = db.query(Message).order_by(Message.id).first()
            conversations.delete_message(self.cid,msg.id,db)
            self.assertFalse(path.exists())
            self.assertEqual(db.query(ContextSummary).count(),0)
            self.assertEqual(db.query(ContextEvent).count(),0)

    async def test_budget_stops_before_request_and_usage_records_unknown(self):
        fixture = ProviderFixture()
        ledger = UsageLedger(input_limit=5, per_output=128)
        with self.assertRaises(ContextLimitError):
            await ledger.invoke(fixture,[HumanMessage(content='long text'*100)])
        self.assertEqual(fixture.calls,[])
        ledger = UsageLedger()
        await ledger.invoke(fixture,[HumanMessage(content='hello')])
        self.assertEqual(ledger.records[0]['usage']['input_tokens'],100)
        class NoUsage(ProviderFixture):
            async def ainvoke(self,messages): return AIMessage(content='answer')
        await ledger.invoke(NoUsage(),[HumanMessage(content='hello')])
        self.assertIsNone(ledger.records[1]['usage'])

    async def test_thirty_materials_reduce_input_without_summary_or_embedding_calls(self):
        self.history(30,1000)
        self.put_setting('chat_input_tokens','8000')
        self.put_setting('chat_compress_model_id','')
        with self.factory() as db:
            pairs=db.query(QAPair).filter_by(state='complete').all()
            baseline=working.estimate_messages([HumanMessage(content=working.text(p)) for p in pairs])
            for pair in pairs:
                update_material(self.cid,MaterialUpdate(pair_id=pair.id,status='completed',result='已完成，保留原始判断标准'),db)
        fixture=ProviderFixture()
        updates=await self.plan(fixture)
        actual=working.estimate_messages(updates[-1]['messages'])
        self.assertLess(actual,baseline//2)
        self.assertEqual(fixture.calls,[])
        self.assertEqual(next(e for e in updates if e['type']=='context_pruned')['count'],30)

    async def test_file_projection_failure_and_external_edit_are_recoverable(self):
        self.history()
        with patch('memory.working.os.replace',side_effect=OSError('disk busy')):
            await self.plan()
        with self.factory() as db:
            head=db.query(ContextSummary).filter_by(active=True).one()
            self.assertEqual(head.projection_state,'pending')
            working.project(db,head);db.commit()
            path=working.summary_path(db,self.cid)
            self.assertEqual(path.read_text(encoding='utf8'),head.markdown)
            path.write_text('user external edit',encoding='utf8')
            working.project(db,head);db.commit()
            self.assertEqual(head.projection_state,'conflict')
            self.assertEqual(path.read_text(encoding='utf8'),'user external edit')

    async def test_deletion_file_failure_does_not_report_success(self):
        self.history();await self.plan()
        with self.factory() as db:
            msg=db.query(Message).order_by(Message.id).first();mid=msg.id
            with patch('memory.working.Path.unlink',side_effect=OSError('locked')):
                with self.assertRaises(OSError):conversations.delete_message(self.cid,mid,db)
            db.rollback()
            self.assertIsNotNone(db.get(Message,mid))
            self.assertEqual(db.query(ContextSummary).count(),1)

    async def test_cancelled_summary_has_no_committed_head_or_background_retry(self):
        self.history()
        started=asyncio.Event()
        class Slow(ProviderFixture):
            async def ainvoke(self,messages):
                self.calls.append(messages);started.set();await asyncio.Event().wait()
        fixture=Slow();ledger=UsageLedger()
        task=asyncio.create_task(self.plan(fixture,ledger))
        await asyncio.wait_for(started.wait(),2)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertEqual(len(fixture.calls),1)
        self.assertEqual(ledger.records[0]['status'],'cancelled')
        with self.factory() as db:self.assertEqual(db.query(ContextSummary).count(),0)

    async def test_retrieval_ledger_reuses_identical_query_vectors(self):
        from providers.telemetry import active_ledger,TrackedClient
        client=MagicMock();client.embed_query.return_value=[1.0,0.0]
        ledger=UsageLedger();token=active_ledger.set(ledger)
        try:
            wrapped=TrackedClient(client,7,'embedding')
            first=await asyncio.to_thread(wrapped.embed_query,'same query')
            second=await asyncio.to_thread(wrapped.embed_query,'same query')
        finally:active_ledger.reset(token)
        self.assertEqual(first,second)
        self.assertEqual(client.embed_query.call_count,1)
        self.assertEqual(ledger.records[0]['category'],'embedding')
        self.assertIsNone(ledger.records[0]['usage'])

    async def test_openai_cumulative_stream_usage_is_not_summed_per_chunk(self):
        class Cumulative(ProviderFixture):
            async def astream(self,messages):
                for n in (1,2,3):
                    yield AIMessageChunk(content='x',usage_metadata={'input_tokens':100,'output_tokens':n,'total_tokens':100+n})
        Cumulative.__module__='langchain_openai.synthetic'
        ledger=UsageLedger(input_limit=200)
        chunks=[c async for c in ledger.stream(Cumulative(),[HumanMessage(content='hello')])]
        self.assertEqual(len(chunks),3)
        self.assertEqual(ledger.input_used,100)
        self.assertEqual(ledger.output_used,3)
        self.assertEqual(ledger.records[0]['usage']['total_tokens'],103)

    async def test_all_four_http_paths_prepare_working_context_and_store_usage(self):
        from knowledge.models import KnowledgeBase
        app = FastAPI(); app.include_router(chat.router); app.include_router(workspace_router)
        def dependency():
            with self.factory() as db: yield db
        app.dependency_overrides[get_db] = dependency
        with self.factory() as db:
            kb = KnowledgeBase(name='isolated', embed_model_id=self.model_id)
            db.add(kb); db.commit(); kb_id=kb.id
        with TestClient(app) as client, patch('chat.router.build_llm',return_value=ProviderFixture()), patch('providers.chat.build_llm',return_value=ProviderFixture()):
            for suffix in ['', '/stream', '/rag', '/rag/stream']:
                payload={'conversation_id':self.cid,'messages':[{'role':'user','content':'question '+suffix}]}
                if 'rag' in suffix: payload['kb_ids']=[kb_id]
                response=client.post(f'/api/chat/{self.model_id}'+suffix,json=payload)
                self.assertEqual(response.status_code,200,response.text)
                if 'stream' in suffix:
                    self.assertIn('context_prepared',response.text)
                    self.assertNotIn('[ERROR]',response.text)
                else:
                    self.assertIn('context_prepared',[a['type'] for a in response.json()['activity']])
            state=client.get(f'/api/memory/conversations/{self.cid}/context').json()
            self.assertEqual(len(state['usage']),4)
        with self.factory() as db:
            self.assertEqual(db.query(ModelUsage).count(),4)
