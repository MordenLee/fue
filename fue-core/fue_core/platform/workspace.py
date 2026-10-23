"""Check compatibility before importing database/bootstrap or migrating any data."""
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fue_core import __version__
from fue_core.platform.installation import write_json

DATA_FORMAT = 1


def prepare_workspace(root):
    root = Path(root)
    manifest = root / 'workspace.json'
    existing = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {}
    if existing:
        if existing.get('data_format_version') != DATA_FORMAT:
            raise ValueError('Workspace data format is incompatible; use a compatible Core. Data was not modified.')
        def version(value):
            return tuple(int(n) for n in value.split('.')[:3])
        if version(existing['last_core_version']) > version(__version__):
            raise ValueError('Workspace was opened by a newer Core; refusing a downgrade.')
    database = root / 'app.db'
    backup = None
    if database.exists() and existing.get('last_core_version') != __version__:
        backup = root / 'backups' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid4().hex[:8])
        backup.mkdir(parents=True)
        with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as source:
            with closing(sqlite3.connect(backup / 'app.db')) as target:
                source.backup(target)
        if existing:
            write_json(backup / 'workspace.json', existing)
    return dict(workspace_id=existing.get('workspace_id') or uuid4().hex,
                data_format_version=DATA_FORMAT, last_core_version=__version__)
