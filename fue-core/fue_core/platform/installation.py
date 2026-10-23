"""Shared, credential-free installation registry. Standard library only."""
import json
import os
import sqlite3
import sys
import time
from contextlib import contextmanager, closing
from pathlib import Path
from uuid import uuid4

from fue_core.platform.lifecycle import InstanceLock


def config_home():
    if os.environ.get('FUE_REGISTRY_PATH'):
        return Path(os.environ['FUE_REGISTRY_PATH']).expanduser().resolve().parent
    if sys.platform == 'win32':
        return Path(os.environ['APPDATA']) / 'fue'
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Application Support/fue'
    return Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'fue'


def registry_path():
    return Path(os.environ.get('FUE_REGISTRY_PATH') or config_home() / 'installation.json').expanduser().resolve()


def empty_registry():
    return dict(schema_version=1, default_workspace=None, default_runtime=None, workspaces={}, runtimes={})


def read_registry():
    path = registry_path()
    if not path.exists():
        return empty_registry()
    data = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(data, dict) or data.get('schema_version') != 1 or
            not isinstance(data.get('workspaces'), dict) or not isinstance(data.get('runtimes'), dict)):
        raise ValueError(f'Unsupported or damaged installation registry: {path}')
    for key, field in [('workspaces', 'data_dir'), ('runtimes', 'core_dir')]:
        for item in data[key].values():
            if not isinstance(item, dict) or not isinstance(item.get(field), str) or not Path(item[field]).is_absolute():
                raise ValueError(f'Invalid {key} entry in {path}')
    return data


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    try:
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def edit_registry():
    lock = InstanceLock(registry_path().parent / '.installation-lock')
    deadline = time.monotonic() + 10
    while True:
        try:
            lock.__enter__()
            break
        except RuntimeError:
            if time.monotonic() > deadline:
                raise
            time.sleep(.1)
    try:
        data = read_registry()
        yield data
        write_json(registry_path(), data)
    finally:
        lock.__exit__()


def inspect_workspace(root):
    root = Path(root).expanduser().resolve()
    database = root / 'app.db'
    if not database.is_file():
        raise ValueError(f'Existing FUE database not found: {database}. Do not initialize an empty replacement.')
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'knowledge_bases', 'document_files', 'conversations', 'providers'} <= tables:
            raise ValueError(f'This is not a FUE workspace: {root}')
        counts = {name: db.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0]
                  for name in ['knowledge_bases', 'document_files', 'conversations']}
    return dict(data_dir=str(root), **counts)


def register_workspace(root, *, name=None, make_default=False):
    info = inspect_workspace(root)
    with edit_registry() as data:
        key = next((key for key, w in data['workspaces'].items()
                    if Path(w['data_dir']).resolve() == Path(info['data_dir'])), None) or uuid4().hex
        old = data['workspaces'].get(key, {})
        data['workspaces'][key] = dict(data_dir=info['data_dir'], name=name or old.get('name') or Path(info['data_dir']).name)
        if make_default or len(data['workspaces']) == 1:
            data['default_workspace'] = key
    return key


def register_runtime(info, *, make_default=False):
    core = Path(info['core_dir']).resolve()
    python = Path(info['python']).resolve()
    if not (core / 'fue.py').is_file() or not python.is_file():
        raise ValueError('Runtime is missing its Core launcher or interpreter')
    with edit_registry() as data:
        key = next((key for key, r in data['runtimes'].items()
                    if Path(r['core_dir']).resolve() == core), None) or uuid4().hex
        data['runtimes'][key] = {**info, 'core_dir': str(core), 'python': str(python)}
        if make_default or len(data['runtimes']) == 1:
            data['default_runtime'] = key
    return key


def select_workspace(key=None):
    data = read_registry()
    key = key or data.get('default_workspace')
    if not key and len(data['workspaces']) == 1:
        key = next(iter(data['workspaces']))
    if not key and data['workspaces']:
        raise ValueError('Multiple workspaces exist. Select a workspace explicitly.')
    if key:
        if key not in data['workspaces']:
            raise ValueError('Registered workspace is missing; choose an existing workspace explicitly')
        item = data['workspaces'][key]
        inspect_workspace(item['data_dir'])
        return dict(id=key, **item)
    return None


def select_runtime():
    data = read_registry()
    key = data.get('default_runtime')
    if not key:
        return None
    if key not in data['runtimes']:
        raise ValueError('Default Core runtime registration is missing')
    item = data['runtimes'][key]
    if not Path(item['python']).is_file() or not (Path(item['core_dir']) / 'fue.py').is_file():
        raise ValueError('Registered Core was moved or removed. Repair the runtime; workspace data is unchanged.')
    if item.get('api_version') != 1 or str(item.get('version', '')).split('.')[0] != '2':
        raise ValueError('Registered Core is incompatible with this FUE client')
    return dict(id=key, **item)
