"""Standard-library client; status/doctor never create data or start Core."""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4


class Client:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def request(self, path, payload=None, method=None, timeout=60):
        discovery = self.root / "runtime" / "core.json"
        if not discovery.exists():
            raise ConnectionError("Core is not running; use core start")
        info = json.loads(discovery.read_text(encoding="utf8"))
        if Path(info["data_dir"]).resolve() != self.root:
            raise ConnectionError("Core discovery points to another data directory")
        port = int(info["port"])
        if not 1 <= port <= 65535:
            raise ConnectionError("Invalid Core port")
        request = Request(f"http://127.0.0.1:{port}/api/v1/{path}",
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Authorization": "Bearer " + info["tokens"]["agent"], "Content-Type": "application/json"},
            method=method or ("POST" if payload is not None else "GET"))
        with urlopen(request, timeout=timeout) as response:
            result = json.load(response)
        if path == "system/status" and result["instance_id"] != info["instance_id"]:
            raise ConnectionError("Core instance identity changed; reconnect")
        if path == 'system/status' and (result.get('api_version', 1) != 1 or
                result.get('data_format_version', 1) != 1 or str(result.get('version', '')).split('.')[0] != '2'):
            raise ValueError('Running Core is incompatible; finish active work and upgrade explicitly')
        return result

    def start(self, initialize=False):
        try:
            return self.request("system/status", timeout=2)
        except (ConnectionError, URLError, TimeoutError, OSError):
            pass
        if not initialize and not (self.root/"app.db").exists():
            raise ValueError("Data directory is not initialized; use core start --init")
        runtime = self.root/"runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        component = Path(__file__).resolve().parents[1]
        command = [sys.executable, "-m", "fue_core.server", "--data-dir", str(self.root)]
        if initialize:
            command.append("--init")
        options = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS} if os.name == "nt" else {"start_new_session": True}
        with (runtime/"core.log").open("ab") as output:
            process = subprocess.Popen(command, cwd=component, stdin=subprocess.DEVNULL,
                                       stdout=output, stderr=output, **options)
        deadline = time.monotonic()+90
        while time.monotonic() < deadline:
            try:
                return self.request("system/status", timeout=2)
            except (ConnectionError, URLError, TimeoutError, OSError):
                if process.poll() is not None:
                    # A concurrent start may have won the directory lock.
                    try:
                        return self.request("system/status", timeout=2)
                    except (ConnectionError, URLError, OSError):
                        raise ConnectionError("Core startup failed; inspect runtime/core.log") from None
                time.sleep(.25)
        raise ConnectionError("Core startup timed out; inspect runtime/core.log")


def parser():
    p = argparse.ArgumentParser(description="FUE Core client")
    p.add_argument("--data-dir", help="Existing FUE data directory")
    p.add_argument("--json", action="store_true")
    p.add_argument("--auto-start", action="store_true", help="Start installed Core if needed; never used for status/doctor")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("doctor")
    c = sub.add_parser("core")
    c.add_argument("action", choices=["start", "stop", "keep-alive"])
    c.add_argument("--init", action="store_true")
    c.add_argument("--enabled", choices=["true", "false"])
    for command in ("libraries", "papers"):
        c = sub.add_parser(command)
        c.add_argument("action", choices=["list"])
        c.add_argument("--limit", type=int, default=50)
        c.add_argument("--offset", type=int, default=0)
        if command == "papers": c.add_argument("--library", type=int, required=True)
    c = sub.add_parser("search")
    c.add_argument("query")
    c.add_argument("--library", type=int, action="append")
    c.add_argument("--mode", choices=["keyword", "vector", "hybrid"], default="keyword")
    c.add_argument("--limit", type=int, default=5)
    c = sub.add_parser("read")
    c.add_argument("ref")
    for name, default in [("before", 0), ("after", 0), ("offset", 0), ("length", 2000)]:
        c.add_argument("--"+name, type=int, default=default)
    c = sub.add_parser("cite")
    c.add_argument("document_id", type=int)
    c.add_argument("--style", default="apa", choices=["apa", "mla", "chicago", "gb_t7714"])
    c = sub.add_parser("memory")
    c.add_argument("action", choices=["search", "read"])
    c.add_argument("value")
    c.add_argument("--days", type=int, choices=[7,30,360])
    c.add_argument("--offset", type=int, default=0)
    c.add_argument("--length", type=int, default=2000)
    c.add_argument("--mode", choices=["keyword", "vector", "hybrid"], default="keyword")
    c = sub.add_parser("tasks")
    c.add_argument("action", choices=["submit", "get", "cancel"])
    c.add_argument("task_id", nargs="?")
    c.add_argument("--file")
    c.add_argument("--after", type=int, default=0)
    return p


def main(argv=None):
    # Accept --json before or after the subcommand without duplicating schemas.
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == 'installation':
        from fue_core.install import main as installation_main
        return installation_main([arg for arg in argv[1:] if arg != '--json'])
    use_json = "--json" in argv
    argv = [x for x in argv if x != "--json"]
    args = parser().parse_args(argv)
    from fue_core.platform.paths import data_dir
    client = Client(args.data_dir or data_dir())
    request_id = str(uuid4())
    try:
        if args.auto_start and args.command not in {"status", "doctor", "core"}:
            client.start()
        if args.command in {"status", "doctor"}:
            result = client.request("system/status", timeout=3)
        elif args.command == "core":
            if args.action == "start": result = client.start(args.init)
            elif args.action == "stop": result = client.request("system/stop", {})
            else:
                if args.enabled is None: raise ValueError("keep-alive requires --enabled true|false")
                result = client.request("system/keep-alive", {"enabled": args.enabled == "true"}, method="PUT")
        elif args.command in {"libraries", "papers"}:
            params = {"offset": args.offset, "limit": args.limit}
            if args.command == "papers": params["library"] = args.library
            result = client.request(f"dataset/{args.command}?"+urlencode(params))
        elif args.command == "search":
            result = client.request("dataset/search", {"query": args.query, "kb_ids": args.library,
                                                       "mode": args.mode, "limit": args.limit})
        elif args.command == "read":
            result = client.request("dataset/read?"+urlencode({k:getattr(args,k) for k in ["ref","before","after","offset","length"]}))
        elif args.command == "cite":
            result = client.request("dataset/cite?"+urlencode({"document_id":args.document_id,"style":args.style}))
        elif args.command == "memory":
            if args.action == "search":
                result = client.request("memory/search", {"query":args.value,"days":args.days,"offset":args.offset,"mode":args.mode})
            else:
                result = client.request("memory/read?"+urlencode({"ref":args.value,"offset":args.offset,"length":args.length}))
        elif args.command == "tasks":
            if args.action == "submit":
                if not args.file: raise ValueError("tasks submit requires --file")
                payload = json.loads(Path(args.file).read_text(encoding="utf8"))
                if not payload.get("request_key"):
                    raise ValueError("Task file requires a stable request_key to prevent duplicate paid execution")
                result = client.request("tasks", payload)
            else:
                if not args.task_id: raise ValueError("Task ID is required")
                result = client.request(f"tasks/{args.task_id}/cancel", {}) if args.action == "cancel" else client.request(f"tasks/{args.task_id}?after={args.after}")
        output, code = {"ok":True, "schema_version":1,"request_id":request_id,"data":result}, 0
    except HTTPError as exc:
        codes = {401:4,403:4,404:5,410:5,422:2,503:3}
        code = codes.get(exc.code,1)
        output = {"ok":False,"schema_version":1,"request_id":request_id,
                  "error":{"code":f"http_{exc.code}","message":exc.read().decode(),"retryable":exc.code==503}}
    except (ConnectionError, URLError, OSError, ValueError) as exc:
        code = 2 if isinstance(exc, ValueError) else 3
        output = {"ok":False,"schema_version":1,"request_id":request_id,
                  "error":{"code":"invalid_input" if code==2 else "core_unavailable","message":str(exc),"retryable":code==3}}
    print(json.dumps(output, ensure_ascii=False, indent=None if use_json else 2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
