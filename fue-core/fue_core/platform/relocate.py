"""Offline, verified workspace copy. Original data remains a rollback source."""
import hashlib
import os
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4
from .installation import inspect_workspace, write_json
from .lifecycle import InstanceLock


def relocate(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError('Source and destination must not overlap')
    if destination.exists():
        raise ValueError('Destination must not exist; no data will be overwritten')
    before = inspect_workspace(source)
    staging = destination.with_name(destination.name + '.migrating-' + uuid4().hex[:8])
    assert staging.parent == destination.parent and staging != source
    destination.parent.mkdir(parents=True, exist_ok=True)
    with InstanceLock(source):
        files = []
        excluded = {'venv', '.venv', '__pycache__', 'runtime', 'logs'}
        for directory, children, names in os.walk(source, followlinks=False):
            children[:] = [name for name in children if name not in excluded]
            for name in children + names:
                path = Path(directory) / name
                relative = path.relative_to(source)
                if path.is_symlink() or (os.name == 'nt' and path.stat().st_file_attributes & 0x400):
                    raise ValueError(f'Linked data must be handled explicitly: {relative}')
                if name in names and path.name not in {'app.db', 'app.db-wal', 'app.db-shm'}:
                    files.append((path, relative))
        staging.mkdir()
        hashes = {}
        for path, relative in files:
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            with path.open('rb') as a, target.open('rb') as b:
                original = hashlib.file_digest(a, 'sha256').hexdigest()
                if original != hashlib.file_digest(b, 'sha256').hexdigest():
                    raise ValueError(f'Copy verification failed: {relative}')
                hashes[relative.as_posix()] = original
        with closing(sqlite3.connect((source/'app.db').as_uri()+'?mode=ro', uri=True)) as old:
            with closing(sqlite3.connect(staging/'app.db')) as new:
                old.backup(new)
                if new.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Database verification failed')
        after = inspect_workspace(staging)
        if any(before[key] != after[key] for key in before if key != 'data_dir'):
            raise ValueError('Workspace record counts changed during migration')
        write_json(staging/'migration-copy.json', {'source': str(source), 'verified_files': hashes,
                                                   'original_preserved': True})
        # Atomic publication in the explicitly selected destination parent.
        staging.replace(destination)
    return {'source': str(source), 'data_dir': str(destination), 'verified_files': len(files),
            'original_preserved': True}
