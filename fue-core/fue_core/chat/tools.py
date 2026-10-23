"""Compatibility import for the Dataset retrieval service."""
import sys
from fue_core.dataset import retrieval
sys.modules[__name__] = retrieval
