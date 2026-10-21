"""One data-directory policy for database, indexes and service discovery."""
import os
import sys
from pathlib import Path


def data_dir():
    configured = os.environ.get("APP_BACKEND_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    # Keep the original development data directory through the component move.
    component = Path(__file__).resolve().parents[2]
    if (component.parent / "package.json").exists():
        return component.parent / "backend"
    if sys.platform == "win32":
        return Path(os.environ["APPDATA"]) / "fue" / "backend-data"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "fue" / "backend-data"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home()/".config")) / "fue" / "backend-data"


def resources_dir():
    return Path(__file__).resolve().parents[1] / "resources"
