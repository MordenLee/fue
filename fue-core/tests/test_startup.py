"""Startup must not eagerly load vector and document indexing dependencies."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


class StartupTests(unittest.TestCase):
    def test_application_import_does_not_load_indexing_engines(self):
        root = Path(__file__).resolve().parents[2]
        env = dict(os.environ, PYTHONPATH=str(root / 'fue-core'),
                   FUE_DATA_DIR=str(root / 'artifacts/tmp/startup-import-test'))
        result = subprocess.run([sys.executable, '-c',
            "import fue_core.app, sys; "
            "assert 'chromadb' not in sys.modules; "
            "assert 'langchain_text_splitters' not in sys.modules"],
            env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
