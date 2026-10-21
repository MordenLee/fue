"""Portable CLI entrypoint, also usable with Studio's bundled Python."""
from fue_core.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
