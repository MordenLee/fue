"""Shared setting lookup; no dependency on chat memory."""
from fue_core.settings.models import Setting, DEFAULTS


def setting(db, key):
    row = db.get(Setting, key)
    return row.value if row else DEFAULTS.get(key, "")
