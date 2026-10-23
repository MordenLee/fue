"""Numbered SQLite migrations, independent of application release versions."""
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from sqlalchemy import inspect, text

SCHEMA_VERSION = 2


def migrate(engine, metadata):
    with engine.connect() as connection:
        tables = inspect(connection).get_table_names()
        version = connection.execute(text('SELECT COALESCE(MAX(version), 0) FROM schema_migrations')).scalar() if 'schema_migrations' in tables else 0
    if version > SCHEMA_VERSION:
        raise RuntimeError('Database schema is newer than this Core; no changes made')
    if version == SCHEMA_VERSION:
        return
    database = engine.url.database
    if database and database != ':memory:' and tables:
        source_path = Path(database).resolve()
        backup = source_path.parent / 'backups' / ('schema-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid4().hex[:8])
        backup.mkdir(parents=True)
        with closing(sqlite3.connect(source_path.as_uri() + '?mode=ro', uri=True)) as source:
            with closing(sqlite3.connect(backup / 'app.db')) as target:
                source.backup(target)
    with engine.connect() as connection:
        # Explicit BEGIN ensures SQLite DDL participates in the transaction.
        connection.exec_driver_sql('BEGIN IMMEDIATE')
        try:
            metadata.create_all(connection)
            columns = {
                'providers': [('sort_order', 'INTEGER NOT NULL DEFAULT 0')],
                'conversations': [('folder_id', 'INTEGER')],
                'knowledge_bases': [('folder_id', 'INTEGER'), ('use_delimiter_split', 'INTEGER NOT NULL DEFAULT 1')],
                'messages': [('model_id', 'INTEGER REFERENCES ai_models(id) ON DELETE SET NULL')],
            }
            for table, additions in columns.items():
                if not inspect(connection).has_table(table):
                    continue
                present = {c['name'] for c in inspect(connection).get_columns(table)}
                for name, sql_type in additions:
                    if name not in present:
                        connection.exec_driver_sql(f'ALTER TABLE {table} ADD COLUMN {name} {sql_type}')
            connection.exec_driver_sql('CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)')
            connection.execute(text('INSERT INTO schema_migrations VALUES (:v, :at)'), {'v': SCHEMA_VERSION, 'at': datetime.now(timezone.utc).isoformat()})
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
