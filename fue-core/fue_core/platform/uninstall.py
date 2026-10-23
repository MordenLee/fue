"""Explicit removal of installer-managed runtimes, preserving every workspace."""
import json
import os
import shutil
import sys
from contextlib import ExitStack
from pathlib import Path

from .installation import edit_registry, registry_path
from .lifecycle import InstanceLock


def remove_managed_runtimes():
    with edit_registry() as registry, ExitStack() as locks:
        workspaces = [Path(w['data_dir']).resolve() for w in registry['workspaces'].values()]
        targets = []
        for key, runtime in registry['runtimes'].items():
            if runtime.get('managed') is not True:
                continue
            core = Path(runtime['core_dir'])
            target = core.parent
            # Validate the exact installer-created directory before any recursive deletion.
            if not target.exists():
                targets.append((key, None))
                continue
            if any(p.is_symlink() or (os.name == 'nt' and p.stat().st_file_attributes & 0x400)
                   for p in [target, *target.parents]):
                raise ValueError('Runtime path contains a link; remove it manually')
            target = target.resolve()
            marker = target / 'runtime.json'
            if core.name != 'core' or not marker.is_file():
                raise ValueError(f'Not an installer-managed runtime directory: {target}')
            metadata = json.loads(marker.read_text(encoding='utf-8'))
            if (metadata.get('managed') is not True or
                    Path(metadata.get('core_dir', '')).resolve() != core.resolve() or
                    Path(metadata.get('python', '')).resolve() != Path(runtime['python']).resolve() or
                    not Path(runtime['python']).resolve().is_relative_to(target)):
                raise ValueError(f'Runtime ownership check failed: {target}')
            protected = [*workspaces, registry_path(), Path(sys.executable), Path(__file__)]
            if any(p.resolve().is_relative_to(target) for p in protected):
                raise ValueError(f'Runtime overlaps data or the running uninstaller: {target}')
            if any(p.name in {'app.db', 'chroma_data', 'workspace.json'} for p in target.rglob('*')):
                raise ValueError(f'Runtime contains workspace data; preserved: {target}')
            targets.append((key, target))
        # Hold workspace locks until deletion finishes, so no Core can start midway.
        for workspace in workspaces:
            if workspace.exists():
                locks.enter_context(InstanceLock(workspace))
        removed = []
        for key, target in targets:
            if target is not None:
                shutil.rmtree(target)
            del registry['runtimes'][key]
            removed.append(key)
        if registry.get('default_runtime') in removed:
            registry['default_runtime'] = None
        return dict(removed=removed, workspaces_preserved=True)
