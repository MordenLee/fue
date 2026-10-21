"""Explicitly backfill and index complete QA pairs with a configured embedding model.

This command sends conversation history to that provider. Run only with authorization.
It prints counts only, never conversation text or credentials. New messages are handled
by the application's background worker after startup.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import Base, engine, SessionLocal
from memory import service
from memory.models import ChatEvent, QAPair
from memory.router import status
from providers.models import AIModel
from settings.models import Setting
import knowledge  # Register document models for foreign key resolution.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embedding-model-id", type=int, required=True)
    parser.add_argument("--query-scope", choices=["disabled", "7", "30", "360", "all"])
    parser.add_argument("--query-mode", choices=["keyword", "rag"])
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    # Additive migration: only the two new tables are created, no existing table rebuilt.
    Base.metadata.create_all(engine, tables=[ChatEvent.__table__, QAPair.__table__])
    with SessionLocal() as db:
        model = db.get(AIModel, args.embedding_model_id)
        if model is None or model.model_type != "embedding" or not model.is_enabled or not model.provider.is_enabled:
            raise SystemExit("Select an enabled embedding model/provider")
        db.merge(Setting(key="memory_embed_model_id", value=str(model.id)))
        if args.query_scope:
            db.merge(Setting(key="memory_query_scope", value=args.query_scope))
        if args.query_mode:
            db.merge(Setting(key="memory_query_mode", value=args.query_mode))
        db.commit()
    service.backfill(SessionLocal)
    with SessionLocal() as db:
        initial = status(db)
    print(json.dumps({"stage": "backfilled", **initial}), flush=True)
    rounds = (initial["pairs"] + 15) // 16 + 1
    for _ in range(rounds):
        service.process_pending(SessionLocal)
        with SessionLocal() as db:
            report = status(db)
        print(json.dumps({"stage": "indexing", **report}), flush=True)
        if report["keyword_indexed"] == report["pairs"] and report["vector_indexed"] + report["vector_errors"] == report["pairs"]:
            return 1 if report["vector_errors"] else 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
