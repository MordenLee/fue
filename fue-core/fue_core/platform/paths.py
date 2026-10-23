"""One data-directory policy for database, indexes and service discovery."""
import os
import json
import sys
from pathlib import Path


def data_dir():
    configured = os.environ.get('FUE_DATA_DIR') or os.environ.get("APP_BACKEND_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    # Keep the original development data directory through the component move.
    component = Path(__file__).resolve().parents[2]
    if ((component.parent / "package.json").exists() and not os.environ.get('FUE_REGISTRY_PATH')
            and os.environ.get('FUE_USE_REGISTERED_WORKSPACE') != '1'):
        selection = component.parent / '.fue-workspace.json'
        if selection.exists():
            root = Path(json.loads(selection.read_text(encoding='utf-8'))['data_dir']).resolve()
            if not (root / 'app.db').is_file():
                raise ValueError('Selected development workspace is missing; no empty replacement created')
            return root
        legacy = component.parent / 'backend'
        return legacy if (legacy / 'app.db').exists() else component.parent / 'workspaces/development'
    from fue_core.platform.installation import select_workspace, config_home
    workspace = select_workspace()
    if workspace:
        return Path(workspace['data_dir'])
    legacy = config_home() / 'backend-data'
    return legacy if (legacy / 'app.db').exists() else config_home() / 'workspaces/default'


def resources_dir():
    return Path(__file__).resolve().parents[1] / "resources"
