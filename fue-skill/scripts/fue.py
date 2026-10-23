"""Locate installed Core, then invoke its standard-library CLI with its Python."""
import os
import json
from pathlib import Path
import subprocess
import sys


def registry_path():
    override = os.environ.get('FUE_REGISTRY_PATH')
    if override:
        return Path(override).expanduser().resolve()
    if os.name == 'nt':
        return Path(os.environ['APPDATA']) / 'fue/installation.json'
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Application Support/fue/installation.json'
    return Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'fue/installation.json'


def registered_connection(workspace=None, data_override=None):
    path = registry_path()
    if not path.exists():
        if workspace:
            raise ValueError('No installation registry; cannot select a registered workspace')
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema_version') != 1:
        raise ValueError('Unsupported installation registry version')
    runtime = data['runtimes'].get(data.get('default_runtime'))
    key = workspace or data.get('default_workspace')
    if not key and len(data['workspaces']) == 1:
        key = next(iter(data['workspaces']))
    selected = data['workspaces'].get(key)
    if not runtime or (not selected and not data_override):
        raise ValueError('No unambiguous Core/workspace selection. Use the installer to select it.')
    if data_override:
        return {**runtime, 'data_dir': str(Path(data_override).expanduser().resolve())}
    if not (Path(selected['data_dir']) / 'app.db').is_file():
        raise ValueError('Registered workspace is missing; refusing to initialize a replacement')
    return {**runtime, 'data_dir': selected['data_dir']}


def main():
    repo = Path(__file__).resolve().parents[2]
    config = {}
    args = list(sys.argv[1:])
    data_override = os.environ.get('FUE_DATA_DIR') or os.environ.get('APP_BACKEND_DATA_DIR')
    if '--data-dir' in args:
        index = args.index('--data-dir')
        if index + 1 == len(args):
            raise ValueError('--data-dir requires a directory')
        data_override = args[index + 1]
    workspace = None
    if '--workspace' in args:
        index = args.index('--workspace')
        if index + 1 == len(args):
            raise ValueError('--workspace requires an ID')
        workspace = args[index + 1]
        del args[index:index + 2]
    package_config = Path(__file__).resolve().parents[1]/'connection.json'
    if workspace:
        config = registered_connection(workspace, data_override)
    elif package_config.exists():
        config = json.loads(package_config.read_text(encoding='utf8'))
        if config.get('workspace_id'):
            config = {**registered_connection(config['workspace_id'], data_override), **config}
    elif registry_path().exists():
        config = registered_connection(data_override=data_override)
    elif os.name == 'nt':
        studio_config = Path(os.environ['APPDATA'])/'fue/core-connection.json'
        if studio_config.exists():
            config = json.loads(studio_config.read_text(encoding='utf8'))
    configured = os.environ.get("FUE_CORE_DIR")
    core = Path(configured or config.get('core_dir') or repo/'fue-core').expanduser().resolve()
    if not (core/"fue.py").is_file():
        print('FUE Core not found. Set FUE_CORE_DIR to its installed Core directory.', file=sys.stderr)
        return 3
    bundled = core.parent/"python"/("python.exe" if os.name=="nt" else "bin/python3")
    local = repo/".venv"/("Scripts/python.exe" if os.name=="nt" else "bin/python3")
    python = os.environ.get("FUE_PYTHON") or config.get('python') or str(bundled if bundled.exists() else local if local.exists() else Path(sys.executable))
    if '--data-dir' not in args and not data_override:
        if config.get('data_dir'):
            args = ['--data-dir',config['data_dir'],*args]
        elif (repo/'.fue-workspace.json').exists():
            args = ['--data-dir', json.loads((repo/'.fue-workspace.json').read_text(encoding='utf-8'))['data_dir'], *args]
        elif (repo/'backend/app.db').exists():
            args = ['--data-dir',str(repo/'backend'),*args]
        elif os.name=='nt':
            args = ['--data-dir',str(Path(os.environ['APPDATA'])/'fue/backend-data'),*args]
        else:
            print('Set APP_BACKEND_DATA_DIR or pass --data-dir for this installation.',file=sys.stderr)
            return 3
    env = dict(os.environ)
    env.pop('PYTHONHOME', None)
    env.pop('PYTHONPATH', None)
    if config.get('python_home') and not os.environ.get('FUE_PYTHON'):
        env['PYTHONHOME'] = config['python_home']
    env['PYTHONIOENCODING'] = 'utf-8'
    return subprocess.call([python,str(core/'fue.py'),*args], env=env)


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError) as exc:
        print(json.dumps({'ok':False,'error':str(exc)}, ensure_ascii=False))
        raise SystemExit(3)
