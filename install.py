"""Install FUE Agent edition from an extracted source or offline bundle."""
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root / 'fue-core'))
from fue_core.install import main

if __name__ == '__main__':
    args = sys.argv[1:]
    if not args or args[0] not in ('inspect', 'select', 'register', 'install', 'remove-core', 'migrate-workspace'):
        args = ['install', *args]
    if args[0] == 'install':
        args += ['--source-core', str(root / 'fue-core')]
        if '--skill-source' not in args:
            args += ['--skill-source', str(root / 'fue-skill')]
        if (root / 'python' / 'python.exe').exists() and '--bundle-python' not in args:
            args += ['--bundle-python', str(root / 'python')]
    raise SystemExit(main(args))
