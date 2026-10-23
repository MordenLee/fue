"""Build an offline Windows Agent edition from the prepared desktop Python runtime."""
import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'fue-core'))
from fue_core import __version__


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, default=ROOT / 'fue-studio/build/python-runtime')
    parser.add_argument('--output', type=Path, default=ROOT / 'fue-studio/dist' / f'fue-agent-{__version__}-windows-x64.zip')
    args = parser.parse_args()
    if not (args.runtime / 'python.exe').is_file() or not (args.runtime / 'pythonw.exe').is_file():
        parser.error('Prepare the portable Windows runtime first; both python.exe and pythonw.exe are required')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    files = [(ROOT / name, name) for name in ['install.py', 'install.ps1']]
    files.append((ROOT / 'docs/design/installation-and-workspaces.md',
                  'docs/design/installation-and-workspaces.md'))
    for directory in ['fue_core']:
        for path in (ROOT / 'fue-core' / directory).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc' and not path.name.startswith('.env'):
                files.append((path, str(path.relative_to(ROOT))))
    for name in ['fue.py', 'main.py', 'requirements.txt', 'pyproject.toml']:
        files.append((ROOT / 'fue-core' / name, 'fue-core/' + name))
    for path in (ROOT / 'fue-skill').rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts and path.name != 'connection.json' and path.suffix != '.pyc':
            files.append((path, str(path.relative_to(ROOT))))
    for path in args.runtime.rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
            files.append((path, 'python/' + path.relative_to(args.runtime).as_posix()))
    with zipfile.ZipFile(args.output, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path, name in files:
            archive.write(path, name)
    with args.output.open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    args.output.with_suffix('.zip.sha256').write_text(checksum + '  ' + args.output.name + '\n', encoding='utf-8')
    print(args.output)


if __name__ == '__main__': main()
