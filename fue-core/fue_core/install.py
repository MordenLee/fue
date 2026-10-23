"""Unified local installer and discovery commands. No model calls or host assumptions."""
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

from fue_core import __version__
from fue_core.platform.installation import (config_home, registry_path, read_registry, edit_registry,
    inspect_workspace, register_workspace, register_runtime, select_workspace, select_runtime, write_json)


def runtime_env(runtime=None):
    env = dict(os.environ)
    env.pop('PYTHONHOME', None)
    env.pop('PYTHONPATH', None)
    env['PYTHONIOENCODING'] = 'utf-8'
    if runtime and runtime.get('python_home'):
        env['PYTHONHOME'] = runtime['python_home']
    return env


def source_revision(core):
    digest = hashlib.sha256()
    root = Path(core) / 'fue_core'
    for path in sorted(root.rglob('*')):
        if path.is_file() and path.suffix in {'.py', '.json', '.md'} and '__pycache__' not in path.parts:
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def probe(core, python, python_home=None):
    core, python = Path(core).resolve(), Path(python).resolve()
    if not (core / 'fue.py').is_file() or not python.is_file():
        raise ValueError('Core launcher or Python interpreter was not found')
    code = ('import json, fastapi, uvicorn, sqlalchemy, chromadb, langchain_core; '
            'from fue_core import __version__; print(json.dumps({"version":__version__,"api_version":1}))')
    runtime = dict(core_dir=str(core), python=str(python), python_home=str(python_home) if python_home else None)
    result = subprocess.run([str(python), '-c', code], cwd=core, env=runtime_env(runtime),
                            capture_output=True, text=True, encoding='utf-8', timeout=90,
                            **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
    if result.returncode:
        raise ValueError('Core dependency check failed: ' + result.stderr[-2000:])
    info = json.loads(result.stdout)
    if info['version'].split('.')[0] != '2':
        raise ValueError('Core major version is incompatible')
    return dict(runtime, **info, source_revision=source_revision(core))


def provision(source, *, python=None, bundle_python=None, install_root=None, register_existing=False, upgrade=False):
    existing = None if upgrade else select_runtime()
    if existing and not upgrade:
        probe(existing['core_dir'], existing['python'], existing.get('python_home'))
        return existing
    source = Path(source).resolve()
    if register_existing:
        info = dict(probe(source, python or sys.executable), managed=False)
    else:
        root = Path(install_root or os.environ.get('FUE_INSTALL_ROOT') or config_home() / 'runtimes').expanduser().resolve()
        target = root / (__version__ + '-' + uuid4().hex[:10])
        if target.is_relative_to(source):
            raise ValueError('Runtime destination must not be inside its source Core directory')
        target.mkdir(parents=True)
        try:
            core = target / 'core'
            # Only application source and dependency manifests, never local user data.
            packages = ['fue_core']
            core.mkdir()
            for name in packages:
                shutil.copytree(source / name, core / name,
                                ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.env*'))
            for name in ['fue.py', 'main.py', 'requirements.txt', 'pyproject.toml']:
                shutil.copy2(source / name, core / name)
            python_home = None
            if bundle_python:
                bundle = Path(bundle_python).resolve()
                if target.is_relative_to(bundle) or (bundle / 'pyvenv.cfg').exists():
                    raise ValueError('Use a portable Python bundle, not a relocatable virtual environment')
                python_home = target / 'python'
                shutil.copytree(bundle, python_home, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
                executable = python_home / ('python.exe' if os.name == 'nt' else 'bin/python3')
            else:
                # Run through the requested base interpreter; never install into its global environment.
                executable = target / 'venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python3')
                subprocess.run([str(python or sys.executable), '-m', 'venv', str(target / 'venv')],
                               check=True, stdout=sys.stderr, env=runtime_env())
                subprocess.run([str(executable), '-m', 'pip', 'install', '--disable-pip-version-check',
                                '-r', str(core / 'requirements.txt')], check=True, stdout=sys.stderr, env=runtime_env())
            info = dict(probe(core, executable, python_home), managed=True)
            write_json(target / 'runtime.json', info)
        except Exception:
            # This directory was freshly created above and never held workspace data.
            if target.resolve().parent == root and target.exists():
                shutil.rmtree(target)
            raise
    key = register_runtime(info, make_default=not upgrade)
    return dict(id=key, **info)


def invoke(runtime, args):
    result = subprocess.run([runtime['python'], str(Path(runtime['core_dir']) / 'fue.py'), *args, '--json'],
                            cwd=runtime['core_dir'], env=runtime_env(runtime), capture_output=True,
                            text=True, encoding='utf-8', timeout=120,
                            **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
    if result.returncode:
        raise ValueError((result.stdout or result.stderr)[-2000:])
    return json.loads(result.stdout)['data']


def install_skill(source, destination, update=False):
    source = Path(source).resolve()
    target = Path(destination).expanduser().resolve() / 'fue-skill'
    if target.is_relative_to(source) or source.is_relative_to(target):
        raise ValueError('Skill installation cannot overlap its source')
    if not (source / 'SKILL.md').is_file():
        raise ValueError('Skill source is missing SKILL.md')
    files = [p for p in source.rglob('*') if p.is_file() and '__pycache__' not in p.parts
             and p.name != 'connection.json' and p.suffix != '.pyc']
    if target.exists():
        same = all((target / p.relative_to(source)).is_file() and
                   (target / p.relative_to(source)).read_bytes() == p.read_bytes() for p in files)
        if same:
            return str(target)
        if not update:
            raise ValueError('Skill already exists with different contents; use --update-skill to back it up and update')
        backup = target.with_name('fue-skill-backup-' + uuid4().hex[:10])
        shutil.copytree(target, backup)
    target.mkdir(parents=True, exist_ok=True)
    for file in files:
        output = target / file.relative_to(source)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, output)
    return str(target)


def inspect_installation():
    data = read_registry()
    workspaces = []
    for key, item in data['workspaces'].items():
        try:
            details = inspect_workspace(item['data_dir'])
            workspaces.append(dict(id=key, **item, **{k:v for k,v in details.items() if k != 'data_dir'}, valid=True))
        except (ValueError, OSError, sqlite3.Error) as exc:
            workspaces.append(dict(id=key, **item, valid=False, error=str(exc)))
    candidates = []
    paths = [config_home() / 'backend-data']
    legacy = config_home() / 'core-connection.json'
    if legacy.exists():
        hints = json.loads(legacy.read_text(encoding='utf-8'))
        if hints.get('data_dir'):
            paths.insert(0, Path(hints['data_dir']))
    known = {str(Path(w['data_dir']).resolve()) for w in workspaces}
    for root in paths:
        if str(root.resolve()) not in known and (root / 'app.db').exists():
            candidates.append(inspect_workspace(root))
            known.add(str(root.resolve()))
    return dict(registry_path=str(registry_path()), default_workspace=data['default_workspace'],
                workspaces=workspaces, candidates=candidates, runtime=select_runtime())


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if sys.version_info < (3, 11):
        print(json.dumps({'ok': False, 'error': 'FUE requires Python 3.11 or newer'}))
        return 1
    parser = argparse.ArgumentParser(description='FUE installation and workspace management')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('inspect')
    relocation = sub.add_parser('migrate-workspace')
    relocation.add_argument('--source', required=True)
    relocation.add_argument('--destination', required=True)
    remove = sub.add_parser('remove-core')
    remove.add_argument('--confirm', action='store_true', required=True)
    select = sub.add_parser('select')
    select.add_argument('workspace')
    register = sub.add_parser('register')
    register.add_argument('--data-dir', required=True)
    register.add_argument('--name')
    register.add_argument('--make-default', action='store_true')
    install = sub.add_parser('install')
    install.add_argument('--source-core', default=str(Path(__file__).resolve().parents[1]))
    install.add_argument('--bundle-python')
    install.add_argument('--python')
    install.add_argument('--install-root')
    install.add_argument('--register-existing', action='store_true', help='Advanced: register user-managed Core/runtime without copying')
    install.add_argument('--upgrade', action='store_true')
    install.add_argument('--skill-source')
    install.add_argument('--skill-dir')
    install.add_argument('--update-skill', action='store_true')
    install.add_argument('--data-dir')
    install.add_argument('--workspace')
    install.add_argument('--name')
    install.add_argument('--init', action='store_true')
    install.add_argument('--make-default', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'inspect':
            result = inspect_installation()
            result['bundled_revision'] = source_revision(Path(__file__).resolve().parents[1])
        elif args.command == 'migrate-workspace':
            from fue_core.platform.relocate import relocate
            result = relocate(args.source, args.destination)
        elif args.command == 'remove-core':
            from fue_core.platform.uninstall import remove_managed_runtimes
            result = remove_managed_runtimes()
        elif args.command == 'register':
            result = dict(workspace=register_workspace(args.data_dir, name=args.name, make_default=args.make_default))
        elif args.command == 'select':
            selected = select_workspace(args.workspace)
            with edit_registry() as data:
                data['default_workspace'] = selected['id']
            result = selected
        else:
            if args.data_dir and args.workspace:
                raise ValueError('Use --data-dir or --workspace, not both')
            if args.skill_dir and not args.skill_source:
                args.skill_source = str(Path(args.source_core).resolve().parent / 'fue-skill')
            if args.data_dir:
                root = Path(args.data_dir).expanduser().resolve()
            else:
                selected = select_workspace(args.workspace)
                if selected:
                    root = Path(selected['data_dir'])
                else:
                    candidates = inspect_installation()['candidates']
                    if len(candidates) > 1:
                        raise ValueError('Multiple legacy workspaces found; pass --data-dir')
                    root = Path(candidates[0]['data_dir']) if candidates else config_home() / 'workspaces/default'
            initialized = (root / 'app.db').exists()
            if initialized:
                inspect_workspace(root)
            elif not args.init:
                raise ValueError(f'New workspace requires --init: {root}')
            elif root.exists() and any(root.iterdir()):
                raise ValueError('Refusing to initialize a nonempty directory without a FUE database')
            if args.upgrade:
                from fue_core.cli import Client
                from urllib.error import URLError
                data = read_registry()
                old = data['runtimes'].get(data.get('default_runtime'))
                if old:
                    if tuple(int(n) for n in old['version'].split('.')[:3]) > tuple(int(n) for n in __version__.split('.')[:3]):
                        raise ValueError('Refusing to replace a newer Core with an older version')
                    # Do not swap or stop a Core held by Studio or active tasks.
                    for workspace in read_registry()['workspaces'].values():
                        discovery = Path(workspace['data_dir']) / 'runtime/core.json'
                        if discovery.exists():
                            try:
                                Client(workspace['data_dir']).request('system/stop', {})
                            except URLError as exc:
                                if hasattr(exc, 'code'):
                                    raise ValueError('Core is in use; close Studio and finish active tasks before upgrading') from exc
                                continue  # Stale discovery; a stopped process does not block repair.
                            deadline = time.monotonic() + 15
                            while discovery.exists() and time.monotonic() < deadline:
                                time.sleep(.1)
                            if discovery.exists():
                                raise ValueError('Core is still shutting down; retry upgrade later')
            runtime = provision(args.source_core, python=args.python, bundle_python=args.bundle_python,
                                install_root=args.install_root, register_existing=args.register_existing, upgrade=args.upgrade)
            status = invoke(runtime, ['--data-dir', str(root), 'core', 'start', *(['--init'] if not initialized else [])])
            if args.upgrade:
                register_runtime({k:v for k,v in runtime.items() if k != 'id'}, make_default=True)
            key = register_workspace(root, name=args.name, make_default=args.make_default)
            skill = install_skill(args.skill_source, args.skill_dir, args.update_skill) if args.skill_dir else None
            if skill and not (Path(skill) / 'connection.json').exists():
                write_json(Path(skill) / 'connection.json', {'workspace_id': key})
            result = dict(workspace_id=key, data_dir=str(root), runtime=runtime, skill=skill,
                          status=status, next='Reload the host if required; Studio discovers this workspace automatically.')
        print(json.dumps(dict(ok=True, data=result), ensure_ascii=False))
        return 0
    except (ValueError, OSError, RuntimeError, sqlite3.Error, subprocess.SubprocessError) as exc:
        print(json.dumps(dict(ok=False, error=str(exc)), ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
