---
name: fue-skill
description: Search and read a local FUE library or FUE conversation memory, cite its sources, or delegate a research task to FUE. Use when the user names FUE or asks to work with their FUE materials.
---

# FUE access

Use the installed FUE Core through `scripts/fue.py`. Read [connection instructions](references/connection.md) when connecting or installing. The script forwards to the Core CLI; it contains no retrieval or memory implementation.

For a new machine, installing this Skill alone is insufficient: use the unified installer described in the connection instructions to install/reuse Core and register its workspace. On Windows, `scripts/fue.ps1` uses the registered Python even if Python is not on PATH. Never initialize an empty workspace to work around a missing registered database. Host history remains outside FUE.

Start with `status --json` and confirm the intended data instance. List libraries and papers when the scope is unknown. Follow pagination. Prefer Direct mode: search, read relevant evidence and adjacent chunks, then cite its source. A search preview is not a full read. An expired evidence reference requires a new search; do not silently replace an old quotation with similar text.

FUE memory contains FUE's own conversations. Search/read it only within the configured access and time scope. The host retains its own history and memory; never upload or synchronize it to FUE.

Use Delegated mode when the user requests FUE to perform a research task. This uses FUE's configured model and budget. Read [research task instructions](references/tasks.md), submit a bounded goal with explicit library IDs, and report progress/results from FUE. An ordinary failed search does not trigger paid delegation.

FUE controls its own cleaning, execution and context. The host controls how it uses the returned material. Report only operations and results actually observed. Write/editor operations are outside this version.
