# Install and connect

The Skill is an entry point, not the Core runtime. On a new machine use the full source checkout or Windows Agent offline bundle and its root installer. The installer installs/reuses Core, registers one workspace, then copies the Skill into the host's explicitly selected skills directory. It does not modify the host's memory system.

From the full distribution:

```text
python install.py inspect
python install.py install --skill-dir <host-skills-directory> --data-dir <existing-FUE-data-directory>
```

For a genuinely new workspace, add `--init` and select an empty directory. Never use `--init` to recover a missing library. A source install requires Python 3.11+ and network access for dependencies; it creates a dedicated virtual environment. The offline Windows distribution includes Python and dependencies: run `powershell -NoProfile -File install.ps1 install --skill-dir <host-skills-directory> --data-dir <directory> --init` without a separate Python installation. Do not claim this bundle is downloadable until an actual release asset is published.

`python scripts/install.py --destination <host-skills-directory>` forwards to that same installer when a sibling or registered Core exists. A standalone copied Skill with no Core source tells you to obtain the full distribution. Repeating an identical install is safe; changing an existing Skill requires `--update-skill`, which preserves a backup and its local connection settings.

The shared registry is `%APPDATA%/fue/installation.json` on Windows, `~/Library/Application Support/fue/installation.json` on macOS, and `$XDG_CONFIG_HOME/fue/installation.json` (default `~/.config/fue/installation.json`) on Linux. `FUE_REGISTRY_PATH` selects an isolated registry. It records runtime/workspace locations, not API keys. Both Studio and this Skill read it. Adding a second workspace does not silently switch the default; use `python install.py select <workspace-id>`, or pass `--workspace <id>` to `scripts/fue.py` for one command.

Explicit environment and per-Skill `connection.json` overrides remain supported. Otherwise the registry takes priority over legacy Studio connection hints. Missing registered paths are errors, never reasons to create a replacement database. Windows Studio's old `%APPDATA%/fue/core-connection.json` is still a legacy discovery fallback when no registry exists.

On Windows an installed Skill can run without `python` on PATH:

```text
powershell -NoProfile -File <skill>/scripts/fue.ps1 status --json
powershell -NoProfile -File <skill>/scripts/fue.ps1 --auto-start libraries list --json
```

For managed runtime updates, use the new distribution's `install.py install --upgrade` with the existing workspace. Active Studio leases/tasks block replacement. Runtimes are installed side by side; startup checks data-format compatibility before bootstrap, backs up SQLite before a version transition, and rejects downgrades. This is not a migration engine for unknown future Chroma formats.

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
