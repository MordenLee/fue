"""Independent Core lifecycle, external scope and durable-task invariants."""
import asyncio
import json
import shutil
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from database import Base, get_db
import providers, knowledge, conversations, folders
import memory.models
from fue_core.platform.lifecycle import Lifecycle, InstanceLock, CoreAccess
from fue_core.system import router as system_router
from fue_core.external import router as external_router
from fue_core.tasks import TaskManager, TaskInput, ResearchTask


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[2] / ('.tmp_core_'+uuid4().hex)
        self.root.mkdir()
        self.now = 0
        self.state = Lifecycle(self.root, clock=lambda:self.now)

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_studio_lease_active_work_and_idle_timeout(self):
        self.state.lease('studio')
        self.now = 30
        self.state.lease('studio')
        self.assertFalse(self.state.expired())
        self.now = 76
        self.assertFalse(self.state.expired())  # Crash expiry starts idle clock.
        self.now = 376
        self.state.active = 1
        self.assertFalse(self.state.expired())
        self.state.active = 0
        self.state.touch()
        self.now = 675
        self.assertFalse(self.state.expired())
        self.now = 676
        self.assertTrue(self.state.expired())
        self.state.set_keep_alive(True)
        self.assertFalse(self.state.expired())
        self.assertTrue(Lifecycle(self.root).keep_alive)

    def test_lock_prevents_second_writer_and_releases_on_exit(self):
        with InstanceLock(self.root):
            with self.assertRaises(RuntimeError):
                with InstanceLock(self.root): pass
        with InstanceLock(self.root): pass

    def test_roles_and_polling_cannot_hold_core_alive(self):
        app = FastAPI()
        app.state.core = self.state
        app.include_router(system_router)
        self.state.server = SimpleNamespace(should_exit=False)
        agent = {'Authorization':'Bearer '+self.state.tokens['agent']}
        studio = {'Authorization':'Bearer '+self.state.tokens['studio']}
        with TestClient(CoreAccess(app,self.state)) as client:
            self.assertEqual(client.get('/api/v1/system/status').status_code,401)
            self.assertEqual(client.post('/api/v1/system/lease',headers=agent,json={'client_id':'x'}).status_code,403)
            self.assertEqual(client.get('/api/settings',headers=agent).status_code,403)
            self.now=301
            self.assertEqual(client.get('/api/v1/system/status',headers=agent).status_code,200)
            self.assertTrue(self.state.expired())
            self.assertEqual(client.post('/api/v1/system/lease',headers=studio,json={'client_id':'x'}).status_code,200)
            self.assertFalse(self.state.expired())
            self.assertEqual(client.post('/api/v1/system/stop',headers=agent,json={}).status_code,409)

    def test_evidence_invalidates_when_source_changes(self):
        from fue_core.dataset.service import evidence_id, read
        doc=SimpleNamespace(id=1,file_path='original.pdf',created_at='a',indexed_at='b',knowledge_base_id=2)
        ref=evidence_id(doc,0,'original content')
        self.assertNotEqual(ref,evidence_id(doc,0,'modified'))
        collection=SimpleNamespace(get=lambda **kw:{'documents':['modified'],'metadatas':[{'chunk_index':0}]})
        db=SimpleNamespace(get=lambda *a:SimpleNamespace(collection_name='kb_2'))
        chroma=SimpleNamespace(get_collection=lambda _:collection)
        with patch('fue_core.dataset.service.document',return_value=doc),patch('fue_core.dataset.service.get_chroma_client',return_value=chroma):
            from fastapi import HTTPException
            with self.assertRaises(HTTPException) as ctx: read(db,ref)
            self.assertEqual(ctx.exception.status_code,410)


class TaskTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.root=Path(__file__).resolve().parents[2]/('.tmp_core_'+uuid4().hex)
        self.root.mkdir()
        self.engine=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
        Base.metadata.create_all(self.engine)
        self.factory=sessionmaker(bind=self.engine,expire_on_commit=False)
        self.state=Lifecycle(self.root)
        self.manager=TaskManager(self.state,self.factory)
        self.payload=TaskInput(request_key='once',goal='synthetic',model_id=1)

    async def asyncTearDown(self):
        await self.manager.close()
        self.engine.dispose()
        shutil.rmtree(self.root)

    async def test_duplicate_submission_runs_once_and_cancel_cannot_complete(self):
        entered=asyncio.Event()
        async def research(*args):
            entered.set()
            await asyncio.sleep(100)
        self.manager.research=research
        with patch('providers.chat.load_chat_model',return_value=object()):
            first=self.manager.submit(self.payload)
            self.assertEqual(first,self.manager.submit(self.payload))
        await entered.wait()
        self.assertEqual(self.state.active,1)
        self.manager.cancel(first)
        await asyncio.gather(*list(self.manager.running.values()),return_exceptions=True)
        with self.factory() as db:
            row=db.get(ResearchTask,first)
            self.assertEqual(row.state,'cancelled')
            self.assertIsNone(row.result)

    async def test_recovery_marks_interrupted_without_reexecution(self):
        with self.factory() as db:
            db.add(ResearchTask(id='old',request_key='old',fingerprint='x',state='running',
                                payload=self.payload.model_dump(),events=[],created_at=0))
            db.commit()
        self.manager.recover()
        with self.factory() as db:
            self.assertEqual(db.get(ResearchTask,'old').state,'interrupted')
        self.assertFalse(self.manager.running)

    async def test_success_persists_result_and_usage_event(self):
        async def research(task_id,payload):
            self.manager.event(task_id,'usage',{'input_tokens':12})
            return {'content':'synthetic result'}
        self.manager.research=research
        with patch('providers.chat.load_chat_model',return_value=object()):
            task_id=self.manager.submit(self.payload)
        await asyncio.gather(*list(self.manager.running.values()))
        with self.factory() as db:
            row=db.get(ResearchTask,task_id)
            self.assertEqual(row.state,'succeeded')
            self.assertEqual(row.events[0]['sequence'],1)
            self.assertEqual(row.result['content'],'synthetic result')

    async def test_research_uses_real_runner_and_budget_ledger_without_studio_conversation(self):
        from test_agents import FakeModel
        from langchain_core.messages import AIMessage
        model = SimpleNamespace(context_length=64)
        llm = FakeModel([AIMessage(content='A synthetic research result')])
        with patch('providers.chat.load_chat_model',return_value=model), patch('providers.chat.build_llm',return_value=llm):
            task_id = self.manager.submit(self.payload)
            await asyncio.gather(*list(self.manager.running.values()))
        with self.factory() as db:
            row = db.get(ResearchTask,task_id)
            self.assertEqual(row.state,'succeeded',row.error)
            self.assertIn('synthetic',row.result['content'])
            self.assertEqual(len(row.result['usage']),1)
        self.assertEqual(len(llm.inputs),1)


if __name__ == '__main__': unittest.main()
