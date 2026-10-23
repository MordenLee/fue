import asyncio
import json
import shutil
import sys
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException
from fue_core.database import Base
from fue_core import providers, knowledge, conversations, folders
from fue_core.chat.service import ChatRequest, _prepare
from fue_core.execution import reserve, finish, recover, Execution, ExecutionEvent, append_event, read_events
from fue_core.platform.migrations import migrate
from fue_core.platform.relocate import relocate


class RefactorTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[2] / 'artifacts/tmp' / uuid4().hex
        self.root.mkdir(parents=True)
        self.engine = create_engine('sqlite:///' + (self.root / 'app.db').as_posix())
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine)

    def tearDown(self):
        self.engine.dispose()
        assert self.root.resolve().is_relative_to(Path(__file__).resolve().parents[2] / 'artifacts/tmp')
        shutil.rmtree(self.root)

    def test_request_id_replays_without_repeating_work_and_rejects_changed_input(self):
        payload = ChatRequest(request_id='same', messages=[{'role':'user', 'content':'hello'}])
        with self.factory() as db:
            key, cached = reserve(db, 1, payload, False)
            self.assertIsNone(cached)
            with self.assertRaises(HTTPException) as conflict:
                reserve(db, 1, payload, False)
            self.assertEqual(conflict.exception.status_code, 409)
            finish(db, key, 'succeeded', {'content':'saved'})
            self.assertEqual(reserve(db, 1, payload, False)[1]['content'], 'saved')
            payload.messages[0].content = 'different'
            with self.assertRaises(HTTPException): reserve(db, 1, payload, False)

    def test_restart_marks_execution_interrupted_without_reexecution(self):
        with self.factory() as db:
            reserve(db, 1, ChatRequest(request_id='restart', messages=[{'role':'user','content':'hello'}]), False)
            recover(db)
            self.assertEqual(db.get(Execution, 'restart').state, 'interrupted')

    def test_cancel_reaches_running_coroutine_and_does_not_retry(self):
        from fue_core.execution import respond, cancel
        async def scenario():
            entered = asyncio.Event()
            async def execute(*args, **kwargs):
                entered.set()
                await asyncio.Event().wait()
            with self.factory() as db:
                payload = ChatRequest(request_id='cancel-me', messages=[{'role':'user','content':'hello'}])
                task = asyncio.create_task(respond(1, payload, db, False, execute))
                await entered.wait()
                self.assertTrue(cancel('cancel-me', db)['cancellation_requested'])
                with self.assertRaises(asyncio.CancelledError): await task
                self.assertEqual(db.get(Execution, 'cancel-me').state, 'cancelled')
                with self.assertRaises(HTTPException): reserve(db, 1, payload, False)
        asyncio.run(scenario())

    def test_http_stream_replay_invokes_model_once(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from fue_core.database import get_db
        from fue_core.chat.router import router
        from fue_core.providers.models import Provider, AIModel
        from test_agents import FakeModel
        from langchain_core.messages import AIMessage
        with self.factory() as db:
            p = Provider(name='fixture', interface_type='openai')
            db.add(p);db.flush()
            model = AIModel(provider_id=p.id, api_name='fixture', display_name='fixture', model_type='chat', context_length=32000)
            db.add(model);db.commit();model_id=model.id
        app=FastAPI();app.include_router(router)
        def sessions():
            with self.factory() as db: yield db
        app.dependency_overrides[get_db]=sessions
        fake=FakeModel([AIMessage(content='one paid operation at most')])
        payload={'request_id':'http-replay','messages':[{'role':'user','content':'hello'}]}
        with TestClient(app) as client, patch('fue_core.chat.service.build_llm',return_value=fake):
            first=client.post(f'/api/chat/{model_id}/stream',json=payload)
            second=client.post(f'/api/chat/{model_id}/stream',json=payload)
        self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(second.status_code,200,second.text)
        self.assertIn('[REPLACE]',second.text)
        self.assertEqual(len(fake.inputs),1)

    def test_disconnect_is_interrupted_not_success_or_explicit_cancel(self):
        from fue_core.execution import respond
        async def scenario():
            entered=asyncio.Event()
            async def execute(*args, **kwargs):
                entered.set()
                await asyncio.Event().wait()
            with self.factory() as db:
                payload=ChatRequest(request_id='disconnect',messages=[{'role':'user','content':'hello'}])
                task=asyncio.create_task(respond(1,payload,db,False,execute))
                await entered.wait();task.cancel()
                with self.assertRaises(asyncio.CancelledError):await task
                self.assertEqual(db.get(Execution,'disconnect').state,'interrupted')
        asyncio.run(scenario())

    def test_shared_event_cursor_is_bounded_and_ordered(self):
        with self.factory() as db:
            for i in range(7): append_event(db, 'research', 'usage_updated', {'input_estimated':i})
            first = read_events(db, 'research', limit=3)
            second = read_events(db, 'research', first[-1]['sequence'], limit=3)
            self.assertEqual(len(first), 3)
            self.assertGreater(second[0]['sequence'], first[-1]['sequence'])
            self.assertEqual(second[0]['run_id'], 'research')

    def test_numbered_migration_backs_up_even_without_app_version_change(self):
        migrate(self.engine, Base.metadata)
        with self.engine.connect() as db:
            self.assertEqual(db.execute(text('SELECT MAX(version) FROM schema_migrations')).scalar(), 2)
        self.assertEqual(len(list((self.root/'backups').glob('*/app.db'))), 1)
        migrate(self.engine, Base.metadata)
        self.assertEqual(len(list((self.root/'backups').glob('*/app.db'))), 1)

    def test_future_schema_is_refused(self):
        migrate(self.engine, Base.metadata)
        with self.engine.begin() as db:
            db.execute(text("INSERT INTO schema_migrations VALUES (999, 'future')"))
        with self.assertRaises(RuntimeError): migrate(self.engine, Base.metadata)

    def test_failed_migration_rolls_back_ddl_and_leaves_backup(self):
        def fail(connection):
            connection.exec_driver_sql('CREATE TABLE half_finished (id INTEGER)')
            raise RuntimeError('synthetic migration failure')
        with patch.object(Base.metadata, 'create_all', side_effect=fail), self.assertRaises(RuntimeError):
            migrate(self.engine, Base.metadata)
        with self.engine.connect() as db:
            self.assertIsNone(db.execute(text("SELECT name FROM sqlite_master WHERE name='half_finished'")).scalar())
        self.assertEqual(len(list((self.root/'backups').glob('*/app.db'))), 1)

    def test_workspace_copy_preserves_original_and_vector_bytes(self):
        vector = self.root/'chroma_data/index.bin'
        vector.parent.mkdir(); vector.write_bytes(b'local vector data')
        destination = self.root.parent / (self.root.name+'-copy')
        try:
            result = relocate(self.root, destination)
            self.assertTrue(result['original_preserved'])
            self.assertEqual(vector.read_bytes(), (destination/'chroma_data/index.bin').read_bytes())
            self.assertTrue((self.root/'app.db').exists())
            with self.assertRaises(ValueError): relocate(self.root, destination)
        finally:
            if destination.exists():
                assert destination.parent == self.root.parent
                shutil.rmtree(destination)

    def test_budget_is_enabled_without_working_memory(self):
        from fue_core.providers.models import Provider, AIModel
        from test_agents import FakeModel
        with self.factory() as db:
            p = Provider(name='fixture', interface_type='openai')
            db.add(p); db.flush()
            model = AIModel(provider_id=p.id, api_name='fixture', display_name='fixture', model_type='chat', context_length=32000)
            db.add(model); db.commit()
            with patch('fue_core.chat.service.build_llm', return_value=FakeModel([])):
                _, runner, _, _ = _prepare(model.id, ChatRequest(messages=[{'role':'user','content':'hello'}]), db, rag=False)
            self.assertEqual(runner.ledger.input_limit, 48000)
            self.assertEqual(runner.ledger.output_limit, 8192)


if __name__ == '__main__': unittest.main()
