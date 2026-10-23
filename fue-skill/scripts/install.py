"""Forward Skill installation to the unified Core/runtime/workspace installer."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from fue import registry_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--destination', required=True, help='Host skills directory; installs a fue-skill child')
    parser.add_argument('--core-dir')
    parser.add_argument('--data-dir')
    parser.add_argument('--python')
    parser.add_argument('--init', action='store_true')
    parser.add_argument('--update-skill', action='store_true')
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    core = Path(args.core_dir or source.parent / 'fue-core')
    python = args.python or sys.executable
    if not (core / 'fue.py').is_file() and registry_path().exists():
        data = json.loads(registry_path().read_text(encoding='utf-8'))
        runtime = data['runtimes'].get(data.get('default_runtime'))
        if runtime:
            core, python = Path(runtime['core_dir']), runtime['python']
    if not (core / 'fue.py').is_file():
        parser.error('Download the full FUE source or Agent bundle and run install.py; a standalone Skill cannot install missing Core source.')
    command = [python, str(core / 'fue.py'), 'installation', 'install', '--source-core', str(core),
               '--skill-source', str(source), '--skill-dir', args.destination]
    if args.data_dir: command += ['--data-dir', args.data_dir]
    if args.python: command += ['--python', args.python]
    if args.init: command += ['--init']
    if args.update_skill: command += ['--update-skill']
    env = dict(os.environ)
    env.pop('PYTHONHOME', None)
    env.pop('PYTHONPATH', None)
    return subprocess.call(command, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
