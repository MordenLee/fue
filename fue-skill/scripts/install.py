"""Copy this skill to an explicitly selected host skill directory."""
import argparse
import json
from pathlib import Path
import shutil
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--destination', required=True, help='Host skills directory; a fue-skill child will be created')
    parser.add_argument('--core-dir')
    parser.add_argument('--data-dir')
    parser.add_argument('--python')
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    target = Path(args.destination).expanduser().resolve()/'fue-skill'
    if target.exists():
        parser.error('Destination already exists; preserve it and choose a fresh directory or update explicitly')
    if target.is_relative_to(source):
        parser.error('Destination cannot be inside this skill package')
    config = {}
    for argument, key in [(args.core_dir,'core_dir'),(args.data_dir,'data_dir'),(args.python,'python')]:
        if argument:
            path = Path(argument).expanduser().resolve()
            if not path.exists(): parser.error(f'{key} does not exist')
            config[key] = str(path)
    shutil.copytree(source,target,ignore=shutil.ignore_patterns('__pycache__','connection.json'))
    if config:
        (target/'connection.json').write_text(json.dumps(config,indent=2),encoding='utf8')
    print(json.dumps({'installed':str(target),'next':'Reload the host if required, then run scripts/fue.py status --json'}))
    return 0


if __name__=='__main__': raise SystemExit(main())
