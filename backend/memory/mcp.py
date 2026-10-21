"""Small read-only MCP JSON-RPC tools server, shared by the Agent's in-process client.

External HTTP access is opt-in through APP_MCP_TOKEN. No arbitrary SQL/collection access.
Streamable HTTP returns JSON responses; server-initiated SSE is not offered (GET 405).
"""

import hmac
import json
import os
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

router = APIRouter()
PROTOCOL_VERSION = "2025-06-18"


async def dispatch(message, bindings):
    request_id, method = message.get("id"), message.get("method")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": request_id, "result": {
            "protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {}},
            "serverInfo": {"name": "FUE Memory", "version": "1.0.0"}}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        tools = [{"name": b.schema.name, "description": b.schema.description,
                  "inputSchema": b.schema.args_schema.model_json_schema()} for b in bindings]
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": tools}}
    if method != "tools/call":
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}}
    params = message.get("params", {})
    binding = next((b for b in bindings if b.schema.name == params.get("name")), None)
    if binding is None:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "Tool unavailable in this scope"}}
    try:
        args = binding.schema.args_schema.model_validate(params.get("arguments", {})).model_dump()
        result = await binding.execute(args)
        from agents.tools import ToolOutput
        result = result if isinstance(result, ToolOutput) else ToolOutput(result)
        return {"jsonrpc": "2.0", "id": request_id, "result": {
            "content": [{"type": "text", "text": result.content}], "isError": False,
            "structuredContent": {"status": result.status}}}
    except Exception as exc:
        return {"jsonrpc": "2.0", "id": request_id, "result": {
            "content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}], "isError": True}}


async def call_in_process(binding, args):
    """First-party Agent invokes the same tools/call dispatcher without HTTP transport."""
    response = await dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                               "params": {"name": binding.schema.name, "arguments": args}}, [binding])
    result = response["result"]
    if result.get("isError"):
        raise ValueError(result["content"][0]["text"])
    from agents.tools import ToolOutput
    return ToolOutput(result["content"][0]["text"], result["structuredContent"]["status"])


@router.post("/api/mcp")
async def endpoint(request: Request):
    token = os.environ.get("APP_MCP_TOKEN", "")
    if not token:
        raise HTTPException(status_code=503, detail="External MCP is disabled; configure APP_MCP_TOKEN")
    if not hmac.compare_digest(request.headers.get("authorization", ""), f"Bearer {token}"):
        raise HTTPException(status_code=401, detail="MCP authentication required")
    origin = request.headers.get("origin")
    if origin and origin != "null" and urlparse(origin).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise HTTPException(status_code=403, detail="MCP origin not allowed")
    if "application/json" not in request.headers.get("content-type", ""):
        raise HTTPException(status_code=415, detail="Expected application/json")
    if "application/json" not in request.headers.get("accept", "") or "text/event-stream" not in request.headers.get("accept", ""):
        raise HTTPException(status_code=406, detail="MCP requires JSON and event-stream Accept types")
    try:
        message = await request.json()
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            raise ValueError()
    except Exception:
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid request"}}, status_code=400)
    if "id" not in message:
        return Response(status_code=202)
    if message.get("method") in {"initialize", "ping"}:
        return JSONResponse(await dispatch(message, []))
    from agents.tools import make_source_bindings, make_knowledge_binding
    from database import SessionLocal
    from knowledge.models import KnowledgeBase
    from memory.service import setting
    requested = request.query_params.get("kb_ids", "")
    try:
        kb_ids = [int(i) for i in requested.split(",") if i][:20]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid kb_ids")
    with SessionLocal() as db:
        if any(db.get(KnowledgeBase, key) is None for key in kb_ids):
            raise HTTPException(status_code=404, detail="Unknown knowledge base")
        history_enabled = setting(db, "memory_query_scope") != "disabled"
    sources = make_source_bindings(kb_ids, SessionLocal)
    bindings = ([make_knowledge_binding(kb_ids, [], SessionLocal)] if kb_ids else [])
    bindings += [b for b in sources if (b.id in {"memory.search", "memory.read"} and history_enabled) or
                 (b.id == "sources.read" and (kb_ids or history_enabled))]
    return JSONResponse(await dispatch(message, bindings))


@router.get("/api/mcp")
def no_server_events():
    return Response(status_code=405)
