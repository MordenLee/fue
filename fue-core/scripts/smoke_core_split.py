"""Real HTTP/CLI smoke on a synthetic data directory, without paid models."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from urllib.request import Request, urlopen

component = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(component))
from fue_core.cli import Client


def main():
    root = component.parent / '.tmp_split_http'
    client = Client(root)
    client.start(initialize=True)
    discovery = json.loads((root/'runtime/core.json').read_text(encoding='utf8'))
    def http(path, payload=None):
        req = Request(f"http://127.0.0.1:{discovery['port']}{path}",
                      data=json.dumps(payload).encode() if payload is not None else None,
                      headers={'Authorization':'Bearer '+discovery['tokens']['studio'],'Content-Type':'application/json'})
        with urlopen(req) as res: return json.load(res)
    try:
        assert client.request('system/status')['instance_id'] == discovery['instance_id']
        assert http('/api/settings')['chat_context_mode'] == 'legacy'
        # Synthetic model metadata: keyword queries never call its endpoint.
        providers = http('/api/providers')
        assert providers
        with sqlite3.connect(root/'app.db') as db:
            embed_id = db.execute("select id from ai_models where model_type='embedding' limit 1").fetchone()
        if not embed_id:
            raise AssertionError('No embedded preset model available for synthetic KB metadata')
        kb = http('/api/knowledge-bases',{'name':'Split synthetic fixture','embed_model_id':embed_id[0]})
        # Seed indexed text locally; original file references remain synthetic.
        os.environ['APP_BACKEND_DATA_DIR'] = str(root)
        from fue_core.database import SessionLocal
        from fue_core.knowledge.documents.models import DocumentFile
        from fue_core.knowledge.chroma import get_chroma_client
        import fue_core.providers.models, knowledge.models, conversations.models
        with SessionLocal() as db:
            doc = DocumentFile(knowledge_base_id=kb['id'],original_filename='fixture.txt',file_path='fixture.txt',
                               file_type='txt',file_size=30,status='indexed',chunk_count=2)
            db.add(doc); db.commit(); db.refresh(doc)
            doc_id=doc.id
        collection = get_chroma_client().get_or_create_collection(kb['collection_name'], embedding_function=None)
        collection.upsert(ids=[f'doc{doc_id}_chunk0',f'doc{doc_id}_chunk1'],
            documents=['Synthetic mango economic evidence','Neighbor context for this synthetic paper'],
            embeddings=[[0.0],[0.0]],metadatas=[{'document_file_id':doc_id,'knowledge_base_id':kb['id'],
                'original_filename':'fixture.txt','chunk_index':index} for index in range(2)])
        hits = client.request('dataset/search',{'query':'mango','kb_ids':[kb['id']],'mode':'keyword','limit':3})
        assert hits['items'],hits
        ref = hits['items'][0]['evidence_id']
        from urllib.parse import urlencode
        read = client.request('dataset/read?'+urlencode({'ref':ref,'after':1}))
        assert 'Neighbor context' in read['text'],read
        assert client.request('dataset/papers?library='+str(kb['id']))['items'][0]['id']==doc_id
        print(json.dumps({'http':'passed','same_instance':True,'keyword_search':True,'neighbor_read':True,'paid_calls':0}))
    finally:
        client.request('system/stop',{})


if __name__=='__main__': main()
