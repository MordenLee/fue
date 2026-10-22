"""Local instance ownership, role-bound access and monotonic idle accounting."""
import asyncio
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from uuid import uuid4


class InstanceLock:
    def __init__(self, root):
        self.path = Path(root) / "runtime" / "core.lock"
        self.file = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")
        try:
            if os.fstat(self.file.fileno()).st_size == 0:
                self.file.write(b"0")
                self.file.flush()
            self.file.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise RuntimeError("A Core instance already owns this data directory") from None
        return self

    def __exit__(self, *_):
        if os.name == "nt":
            import msvcrt
            self.file.seek(0)
            msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
        self.file.close()


class Lifecycle:
    def __init__(self, root, *, idle_seconds=300, clock=time.monotonic):
        self.root = Path(root).resolve()
        self.clock, self.idle_seconds = clock, idle_seconds
        self.instance_id = str(uuid4())
        self.tokens = {role: secrets.token_urlsafe(32) for role in ("studio", "agent")}
        self.leases = {}
        self.active = 0
        self.last_activity = clock()
        self.closing = False
        self.server = None
        self.port = None
        self.busy_probe = lambda: False
        self.was_busy = False
        self.config_path = self.root / "runtime" / "core-config.json"
        self.keep_alive = False
        self.allowed_libraries = None
        if self.config_path.exists():
            config = json.loads(self.config_path.read_text(encoding="utf8"))
            self.keep_alive = config.get("keep_alive", False) is True
            self.allowed_libraries = config.get("allowed_libraries")
            if self.allowed_libraries is not None and (not isinstance(self.allowed_libraries, list) or
                    any(type(n) is not int for n in self.allowed_libraries)):
                raise ValueError("Invalid allowed_libraries in Core configuration")

    def identity(self, token):
        return next((role for role, secret in self.tokens.items()
                     if hmac.compare_digest(secret, token)), None)

    def touch(self):
        self.last_activity = self.clock()

    def lease(self, client_id):
        self.leases[client_id] = self.clock() + 45

    def release(self, client_id):
        if self.leases.pop(client_id, None) is not None:
            self.touch()

    def expired(self):
        now = self.clock()
        stale = [key for key, until in self.leases.items() if until <= now]
        for key in stale:
            self.release(key)
        return (not self.keep_alive and not self.leases and not self.active
                and now - self.last_activity >= self.idle_seconds)

    def publish(self, port):
        self.port = port
        self.write_json(self.root / "runtime" / "core.json", {
            "schema_version": 1, "instance_id": self.instance_id, "data_dir": str(self.root),
            "pid": os.getpid(), "port": port, "tokens": self.tokens,
        })

    @staticmethod
    def write_json(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf8")
        if os.name != "nt":
            temporary.chmod(0o600)
        temporary.replace(path)

    def set_keep_alive(self, enabled):
        self.write_json(self.config_path, {"keep_alive": enabled, "allowed_libraries": self.allowed_libraries})
        self.keep_alive = enabled
        self.touch()

    def cleanup(self):
        path = self.root / "runtime" / "core.json"
        if path.exists() and json.loads(path.read_text(encoding="utf8")).get("instance_id") == self.instance_id:
            path.unlink()

    async def supervise(self):
        while True:
            await asyncio.sleep(1)
            busy = self.busy_probe()
            if busy or self.was_busy:
                self.touch()
            self.was_busy = busy
            if busy:
                continue
            if self.expired():
                self.closing = True
                self.server.should_exit = True
                return


class CoreAccess:
    """Pure ASGI wrapper: streaming and response background work stay active."""
    def __init__(self, app, lifecycle):
        self.app, self.lifecycle = app, lifecycle

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        from starlette.responses import JSONResponse
        headers = dict(scope.get("headers", []))
        token = headers.get(b"authorization", b"").decode().removeprefix("Bearer ")
        role = self.lifecycle.identity(token)
        path = scope["path"]
        legacy_mcp = False
        if path == "/api/mcp":
            legacy_token = os.environ.get("APP_MCP_TOKEN", "")
            legacy_mcp = bool(legacy_token and hmac.compare_digest(legacy_token, token))
            if legacy_mcp:
                role = "agent"
        if path == "/api/ping":
            return await self.app(scope, receive, send)
        if not role:
            return await JSONResponse({"detail": "Core authentication required"}, 401)(scope, receive, send)
        if role == "agent" and not path.startswith("/api/v1/") and not legacy_mcp:
            return await JSONResponse({"detail": "Agent access is limited to the external API"}, 403)(scope, receive, send)
        if self.lifecycle.closing:
            return await JSONResponse({"detail": "Core is stopping; reconnect"}, 503)(scope, receive, send)
        scope.setdefault("state", {})["core_role"] = role
        if legacy_mcp and self.lifecycle.allowed_libraries is not None:
            from urllib.parse import parse_qs
            try:
                query = parse_qs(scope.get("query_string", b"").decode())
                selected = [int(n) for n in query.get("kb_ids", [""])[0].split(",") if n]
                if not set(selected) <= set(self.lifecycle.allowed_libraries):
                    raise ValueError()
            except ValueError:
                return await JSONResponse({"detail": "Library scope denied"}, 403)(scope, receive, send)
        quiet = path.startswith("/api/v1/system/") or (scope["method"] == "GET" and path.startswith("/api/v1/tasks"))
        self.lifecycle.active += 1
        if not quiet:
            self.lifecycle.touch()
        try:
            await self.app(scope, receive, send)
        finally:
            self.lifecycle.active -= 1
            if not quiet:
                self.lifecycle.touch()
