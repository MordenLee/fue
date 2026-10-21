# Core external contract v1

The actual OpenAPI schema is available from a Studio-authenticated Core connection at `/openapi.json`. Request validation is defined in Python Pydantic models; this file records semantics rather than duplicating every field.

## Transport

Core binds to loopback only. The data directory's `runtime/core.json` records instance identity, port and role-bound credentials. Requests use `Authorization: Bearer ...`. Studio can use compatibility APIs; Agent credentials only access `/api/v1/*`. Explicit legacy `APP_MCP_TOKEN` access retains `/api/mcp` behavior.

CLI wraps API results as `{ok, schema_version: 1, request_id, data}` or `{ok: false, schema_version: 1, request_id, error: {code, message, retryable}}`. HTTP compatibility APIs retain their original FastAPI response shapes. CLI exit codes: 0 success, 2 input, 3 unavailable, 4 denied, 5 missing/expired source, 1 other failure.

## Endpoints

| Method/path under `/api/v1` | Meaning |
| --- | --- |
| GET `system/status` | Instance, data directory, capabilities and lifecycle settings |
| POST `system/lease`, `system/release` | Studio-only expiring hold |
| PUT `system/keep-alive` | Persist optional background mode |
| POST `system/stop` | Stop only when no Studio or active work holds Core |
| GET `dataset/libraries`, `dataset/papers` | `offset`/`limit` paging, `next_offset`, `complete` |
| POST `dataset/search` | Bounded previews, stable evidence IDs, unindexed count |
| GET `dataset/read` | Evidence with neighboring chunks, character paging |
| GET `dataset/cite` | Existing citation metadata formatted by requested style |
| POST `memory/search` | Existing QA search/time scope; read-only |
| GET `memory/read` | Direct chat/material/compaction reference read |
| POST `tasks` | Durable idempotent task submission |
| GET `tasks/{id}` | State, bounded event page, result and usage |
| POST `tasks/{id}/cancel` | Prevent further execution and late success |

Evidence IDs bind document identity, indexed timestamp, chunk location and text hash. They invalidate on change rather than retargeting. This initial contract reports text as `indexed` and unknown page as null; it does not claim historical raw/clean version storage already exists.

Task states: queued, running, succeeded, failed, cancelled, interrupted. The current worker does not publish partial success. `request_key` uniquely identifies a submission; mismatched reuse conflicts. Restart never silently replays a paid task.

Health/status polling does not extend idle lifetime. Studio holds a renewable 45-second lease; normal renewal is every 10 seconds. Core exits after 300 seconds without Studio, active work or business activity unless keep-alive is enabled.
