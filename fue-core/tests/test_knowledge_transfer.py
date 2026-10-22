"""Offline HTTP round trips using real SQLite and Chroma; no provider calls."""
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import chromadb
from chromadb.config import Settings
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from database import Base, get_db
import providers, knowledge, conversations, folders
from providers.models import Provider, AIModel
from knowledge.models import KnowledgeBase
from knowledge.documents.models import DocumentFile, Citation
from knowledge.router import router
from knowledge.documents.router import router as documents_router
from knowledge.transfer import PROFILE_KEY, profile, digest
from fue_core.dataset import service


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, expire_on_commit=False)()
        self.chroma = chromadb.EphemeralClient(settings=Settings(anonymized_telemetry=False))
        self.before = {c.name for c in self.chroma.list_collections()}
        app = FastAPI()
        app.include_router(router)
        app.include_router(documents_router)
        def session():
            yield self.db
        app.dependency_overrides[get_db] = session
        self.http = TestClient(app)
        self.patches = [patch('knowledge.chroma.get_chroma_client', return_value=self.chroma),
                        patch('fue_core.dataset.service.get_chroma_client', return_value=self.chroma),
                        patch('providers.embeddings.build_embedder', side_effect=AssertionError('Paid embedding call')),
                        patch('providers.chat.build_llm', side_effect=AssertionError('Paid chat call'))]
        for p in self.patches: p.start()
        provider = Provider(name='offline', interface_type='openai_compatible', api_base_url='https://example.invalid/v1', api_key='SECRET-DO-NOT-EXPORT')
        self.db.add(provider)
        self.db.flush()
        self.model = AIModel(provider_id=provider.id, api_name='fixture-embedding', display_name='Fixture', model_type='embedding')
        self.db.add(self.model)
        self.db.flush()
        self.kb = KnowledgeBase(name='中文知识库', embed_model_id=self.model.id, collection_name='test_'+uuid4().hex)
        self.db.add(self.kb)
        self.db.flush()
        self.collection = self.chroma.create_collection(self.kb.collection_name, metadata={PROFILE_KEY:json.dumps(profile(self.model))})
        for i in range(2):
            doc = DocumentFile(knowledge_base_id=self.kb.id, original_filename='same.pdf', file_path='private-source.pdf',
                               file_type='pdf', file_size=123, status='indexed', chunk_count=2, abstract=f'abstract {i}')
            self.db.add(doc)
            self.db.flush()
            self.db.add(Citation(document_file_id=doc.id, title=f'Citation {i}', authors=['Author'], year=2025, doi=f'10.1234/{i}'))
            self.collection.add(ids=[f'doc{doc.id}_chunk{n}' for n in range(2)],
                documents=[f'innovation evidence {i}', f'context following {i}'], embeddings=[[1., float(i+1), .5],[.1, float(i+1), 1.]],
                metadatas=[dict(document_file_id=doc.id, knowledge_base_id=self.kb.id, original_filename='same.pdf', chunk_index=n) for n in range(2)])
        self.db.commit()

    def tearDown(self):
        self.http.close()
        for p in reversed(self.patches): p.stop()
        for c in self.chroma.list_collections():
            if c.name not in self.before: self.chroma.delete_collection(c.name)
        self.db.close()
        self.engine.dispose()

    def export(self):
        response = self.http.get(f'/api/knowledge-bases/{self.kb.id}/export')
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def upload(self, data, **fields):
        return self.http.post('/api/knowledge-bases/import', data={'embed_model_id':str(self.model.id), **fields},
                              files={'file':('kb.json',json.dumps(data).encode(), 'application/json')})

    def resign(self, data):
        data.pop('sha256', None)
        data['sha256'] = digest(data)
        return data

    def test_round_trip_vectors_citations_duplicate_names_and_context(self):
        data = self.export()
        self.assertNotIn('SECRET-DO-NOT-EXPORT', json.dumps(data))
        self.assertNotIn('private-source.pdf', json.dumps(data))
        result = self.upload(data, kb_name='Restored')
        self.assertEqual(result.status_code, 201, result.text)
        result = result.json()
        self.assertEqual((result['documents_created'], result['chunks_imported']), (2,4))
        target = self.db.get(KnowledgeBase, result['knowledge_base']['id'])
        self.assertEqual(target.name, 'Restored')
        self.assertEqual(len(target.documents),2)
        self.assertEqual({d.citation.title for d in target.documents}, {'Citation 0','Citation 1'})
        exported_again = self.http.get(f'/api/knowledge-bases/{target.id}/export').json()
        for before, after in zip(data['documents'],exported_again['documents']):
            self.assertEqual(before['chunks'],after['chunks'])
            self.assertEqual(before['citation'],after['citation'])
        hits = self.http.get(f'/api/knowledge-bases/{target.id}/search',params={'q':'innovation','search_type':'keyword'} )
        self.assertEqual(hits.status_code,200,hits.text)
        self.assertTrue(hits.json())
        doc=target.documents[0]
        ref=service.evidence_id(doc,0,'innovation evidence 0')
        context=service.read(self.db,ref,after=1)
        self.assertIn('context following 0',json.dumps(context))
        collection=self.chroma.get_collection(target.collection_name)
        self.assertEqual(len(collection.query(query_embeddings=[[1.,1.,.5]], n_results=2)['ids'][0]),2)

    def test_corrupt_checksum_and_malformed_json_leave_no_records(self):
        data=self.export()
        data['documents'][0]['chunks'][0]['content']='tampered'
        for value in (data, [], {'format_version':'1.0'}):
            self.assertEqual(self.upload(value).status_code,400)
        self.assertEqual(self.db.query(KnowledgeBase).count(),1)

    def test_invalid_vectors_indices_and_document_links(self):
        original=self.export()
        for mutation in (
            lambda p:p['documents'][0]['chunks'][0].update(embedding=[]),
            lambda p:p['documents'][0]['chunks'][0].update(embedding=[0.,0.,0.]),
            lambda p:p['documents'][0]['chunks'][0].update(embedding=[1.,2.]),
            lambda p:p['documents'][0]['chunks'][0].update(index=1),
            lambda p:p['documents'][1].update(id=p['documents'][0]['id']),
        ):
            data=copy.deepcopy(original)
            mutation(data)
            self.assertEqual(self.upload(self.resign(data)).status_code,400)
        self.assertEqual(self.db.query(KnowledgeBase).count(),1)

    def test_model_mismatch_is_blocked(self):
        data=self.export()
        self.model.api_name='other-model'
        self.db.commit()
        self.assertEqual(self.upload(data).status_code,409)

    def test_legacy_provenance_requires_confirmation_and_stays_unverified(self):
        self.collection.modify(metadata={'legacy':True})
        data=self.export()
        self.assertFalse(data['profile_verified'])
        self.assertEqual(self.upload(data).status_code,409)
        response=self.upload(data,confirm_unverified='true')
        self.assertEqual(response.status_code,201,response.text)
        target=response.json()['knowledge_base']['id']
        self.assertFalse(self.http.get(f'/api/knowledge-bases/{target}/export').json()['profile_verified'])

    def test_chroma_failure_rolls_back_sqlite_and_collection(self):
        data=self.export()
        from chromadb.api.models.Collection import Collection
        original_add = Collection.add
        calls = []
        def fail_after_first_batch(collection, *args, **kwargs):
            calls.append(collection.name)
            if len(calls) > 1:
                raise RuntimeError('disk failure after partial write')
            return original_add(collection, *args, **kwargs)
        with patch.object(Collection,'add',new=fail_after_first_batch):
            with self.assertRaises(RuntimeError): self.upload(data)
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.db.query(KnowledgeBase).count(),1)
        self.assertEqual({c.name for c in self.chroma.list_collections()}, self.before | {self.kb.collection_name})

    def test_imported_documents_cannot_lose_index_via_reindex(self):
        response=self.upload(self.export()).json()
        kb=self.db.get(KnowledgeBase,response['knowledge_base']['id'])
        doc=kb.documents[0]
        response=self.http.post(f'/api/knowledge-bases/{kb.id}/documents/{doc.id}/reindex')
        self.assertEqual(response.status_code,409)
        response=self.http.post(f'/api/knowledge-bases/{kb.id}/documents/batch-reindex',json={'doc_ids':[doc.id]})
        self.assertEqual(response.status_code,409)
        self.assertEqual(self.chroma.get_collection(kb.collection_name).count(),4)


if __name__ == '__main__': unittest.main()
