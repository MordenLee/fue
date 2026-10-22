# Install and connect

The package is the `fue-skill` directory. Install/copy it into the host's supported skill directory using that host's normal mechanism. Preserve an existing package/configuration; reload if the host requires it. This package does not install or modify the host's memory system.

`python scripts/install.py --destination <host-skills-directory>` copies the package into a `fue-skill` child and refuses to overwrite an existing installation. Optional `--core-dir`, `--data-dir`, `--python` save explicit connection paths. On Windows, Studio also writes non-secret connection hints into `%APPDATA%/fue/core-connection.json`; an installed Skill reads these automatically after Studio has run once. Environment overrides take priority.

In a source checkout, `scripts/fue.py` finds the sibling `fue-core` and repository Python environment automatically. For a desktop installation, configure:

- `FUE_CORE_DIR`: installed `resources/backend` directory containing `fue.py`.
- `APP_BACKEND_DATA_DIR`: existing data directory. Windows defaults to `%APPDATA%/fue/backend-data` through the wrapper.
- `FUE_PYTHON`: optional interpreter override; the wrapper otherwise finds bundled Python.

Run with an available Python interpreter (replace paths for the installation):

```text
python <skill>/scripts/fue.py status --json
python <skill>/scripts/fue.py --auto-start libraries list --json
python <skill>/scripts/fue.py papers list --library 3 --limit 50 --offset 0 --json
python <skill>/scripts/fue.py search "query" --library 3 --mode keyword --json
python <skill>/scripts/fue.py read ev_ID --before 1 --after 1 --json
python <skill>/scripts/fue.py cite 12 --style apa --json
python <skill>/scripts/fue.py memory search "query" --days 30 --json
python <skill>/scripts/fue.py memory read chat:PAIR_ID --json
```

`status`/`doctor` never initialize or start Core. `--auto-start` explicitly allows starting installed Core for a business command, using the existing data directory. First initialization requires `core start --init` and is not the response to a missing connection to an existing library.

Core follows Studio; Agent access keeps it available until five minutes of genuine idle time. Long tasks prevent idle exit. `core keep-alive --enabled true` enables persistent background running; `false` restores idle shutdown. No system service is required.

Read stdout as one JSON result; diagnostics use stderr. Follow `next_offset`. Empty results differ from denied access, unavailable indexes and connection errors. Keyword mode avoids semantic query embedding; vector/hybrid may call configured embedding/rerank models. Follow the user's selected mode.

The local discovery file contains credentials. Never include it in prompts, reports or version control. `runtime/core-config.json` in the data directory supports `allowed_libraries` (list of IDs; `null` means all local libraries) and `keep_alive`. Changes to library grants are loaded on Core restart. Chat reads also obey FUE's history setting.
