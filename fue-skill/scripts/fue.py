"""Locate installed Core, then invoke its standard-library CLI with its Python."""
import os
import json
from pathlib import Path
import subprocess
import sys


def main():
    repo = Path(__file__).resolve().parents[2]
    config = {}
    package_config = Path(__file__).resolve().parents[1]/'connection.json'
    if package_config.exists():
        config = json.loads(package_config.read_text(encoding='utf8'))
    elif os.name == 'nt':
        studio_config = Path(os.environ['APPDATA'])/'fue/core-connection.json'
        if studio_config.exists():
            config = json.loads(studio_config.read_text(encoding='utf8'))
    configured = os.environ.get("FUE_CORE_DIR")
    core = Path(configured or config.get('core_dir') or repo/'fue-core').expanduser().resolve()
    if not (core/"fue.py").is_file():
        print('FUE Core not found. Set FUE_CORE_DIR to its installed backend directory.', file=sys.stderr)
        return 3
    bundled = core.parent/"python"/("python.exe" if os.name=="nt" else "bin/python3")
    local = repo/".venv"/("Scripts/python.exe" if os.name=="nt" else "bin/python3")
    python = os.environ.get("FUE_PYTHON") or config.get('python') or str(bundled if bundled.exists() else local if local.exists() else Path(sys.executable))
    args = list(sys.argv[1:])
    if '--data-dir' not in args and 'APP_BACKEND_DATA_DIR' not in os.environ:
        if config.get('data_dir'):
            args = ['--data-dir',config['data_dir'],*args]
        elif (repo/'backend/app.db').exists():
            args = ['--data-dir',str(repo/'backend'),*args]
        elif os.name=='nt':
            args = ['--data-dir',str(Path(os.environ['APPDATA'])/'fue/backend-data'),*args]
        else:
            print('Set APP_BACKEND_DATA_DIR or pass --data-dir for this installation.',file=sys.stderr)
            return 3
    return subprocess.call([python,str(core/'fue.py'),*args])


if __name__=='__main__': raise SystemExit(main())
