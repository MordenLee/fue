"""Core launcher: owns the data directory before importing database/bootstrap."""
import argparse
import asyncio
import os
import socket

from fue_core.platform.paths import data_dir
from fue_core.platform.lifecycle import InstanceLock, Lifecycle, CoreAccess


def run(argv=None):
    parser = argparse.ArgumentParser(description="Run FUE Core")
    parser.add_argument("--data-dir")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--init", action="store_true", help="Explicitly allow a new data directory")
    args = parser.parse_args(argv)
    if args.data_dir:
        os.environ['FUE_DATA_DIR'] = args.data_dir
        os.environ["APP_BACKEND_DATA_DIR"] = args.data_dir
    root = data_dir()
    if not args.init and not (root / "app.db").exists():
        parser.error("Data directory is not initialized; use --init for first startup")
    with InstanceLock(root):
        from fue_core.platform.workspace import prepare_workspace
        from fue_core.platform.installation import write_json
        manifest = prepare_workspace(root)
        state = Lifecycle(root)
        import uvicorn
        from fue_core.app import app
        app.state.workspace_manifest = manifest
        port = args.port if args.port is not None else int(os.environ.get('FUE_CORE_PORT') or os.environ.get("APP_BACKEND_PORT") or 0)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", port))
        app.state.core = state
        app.state._backend_port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(CoreAccess(app, state), log_level="info"))
        state.server = server

        async def serve():
            try:
                await server.serve(sockets=[sock])
            finally:
                state.cleanup()
                sock.close()
        asyncio.run(serve())


if __name__ == "__main__":
    run()
