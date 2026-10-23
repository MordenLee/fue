"""Instance/lifecycle API; data scope is bound by Core configuration."""
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from fue_core import __version__

router = APIRouter(prefix="/api/v1/system")


@router.get("/status")
def status(request: Request):
    state = request.app.state.core
    return {"schema_version": 1, "api_version": 1, "data_format_version": 1,
            "version": __version__, "instance_id": state.instance_id,
            "data_dir": str(state.root), "role": request.state.core_role,
            "keep_alive": state.keep_alive, "studio_clients": len(state.leases),
            "idle_seconds": state.idle_seconds,
            "capabilities": ["dataset", "memory.read", "tasks", "executions", "numbered_migrations"]}


class Lease(BaseModel):
    client_id: str = Field(min_length=1, max_length=100)


@router.post("/lease")
def lease(payload: Lease, request: Request):
    if request.state.core_role != "studio":
        raise HTTPException(403, "Only Studio can hold a lease")
    request.app.state.core.lease(payload.client_id)
    return {"ok": True}


@router.post("/release")
def release(payload: Lease, request: Request):
    if request.state.core_role != "studio":
        raise HTTPException(403, "Only Studio can release a lease")
    request.app.state.core.release(payload.client_id)
    return {"ok": True}


class KeepAlive(BaseModel):
    enabled: bool


@router.put("/keep-alive")
def keep_alive(payload: KeepAlive, request: Request):
    request.app.state.core.set_keep_alive(payload.enabled)
    return {"keep_alive": payload.enabled}


@router.post("/stop")
def stop(request: Request):
    state = request.app.state.core
    if state.leases or state.active > 1:
        raise HTTPException(409, "Core is in use by Studio or an active task")
    state.closing = True
    state.server.should_exit = True
    return {"stopping": True}
