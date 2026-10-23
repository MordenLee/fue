"""Installation order, workspace selection and compatibility without user data."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import unittest
from contextlib import closing
from unittest.mock import patch
from uuid import uuid4

(Path(__file__).resolve().parents[2] / 'artifacts/tmp').mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fue_core.platform.installation import (read_registry, registry_path, register_workspace,
    register_runtime, select_workspace, select_runtime, edit_registry, write_json)
from fue_core.platform.workspace import prepare_workspace
from fue_core.install import install_skill, inspect_installation
from fue_core.install import provision

REPO = Path(__file__).resolve().parents[2]


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.root = (REPO / 'artifacts/tmp') / ('.tmp_install_test_' + uuid4().hex)
        self.root.mkdir()
        self.env = patch.dict(os.environ, {'FUE_REGISTRY_PATH': str(self.root / 'config/installation.json')})
        self.env.start()
        self.home = patch('fue_core.install.config_home', return_value=self.root / 'config')
        self.home.start()

    def tearDown(self):
        self.home.stop()
        self.env.stop()
        shutil.rmtree(self.root)

    def workspace(self, name):
        root = self.root / name
        root.mkdir()
        with closing(sqlite3.connect(root / 'app.db')) as db:
            for table in ['knowledge_bases','document_files','conversations','providers']:
                db.execute(f'CREATE TABLE {table} (id INTEGER PRIMARY KEY, name TEXT)')
            db.execute("INSERT INTO knowledge_bases(name) VALUES ('Existing library')")
            db.commit()
        return root

    def runtime(self):
        core = self.root / 'runtime/core'
        core.mkdir(parents=True)
        (core / 'fue.py').write_text('')
        executable = core.parent / 'python.exe'
        executable.write_text('')
        return dict(core_dir=str(core), python=str(executable), version='2.0.0', api_version=1, managed=True)

    def test_inspect_never_initializes_or_writes(self):
        result = inspect_installation()
        self.assertEqual(result['workspaces'], [])
        self.assertFalse(registry_path().exists())
        self.assertFalse((self.root / 'config').exists())

    def test_remove_core_preserves_workspaces_and_unmanaged_runtime(self):
        from fue_core.platform.uninstall import remove_managed_runtimes
        workspace = self.workspace('shared')
        register_workspace(workspace)
        original = (workspace / 'app.db').read_bytes()
        runtime = self.runtime()
        write_json(Path(runtime['core_dir']).parent / 'runtime.json', runtime)
        key = register_runtime(runtime)
        unmanaged = dict(runtime, core_dir=str(self.root / 'external'), managed=False)
        Path(unmanaged['core_dir']).mkdir()
        (Path(unmanaged['core_dir']) / 'fue.py').write_text('')
        external_key = register_runtime(unmanaged)
        self.assertEqual(remove_managed_runtimes()['removed'], [key])
        self.assertFalse(Path(runtime['core_dir']).parent.exists())
        self.assertEqual((workspace / 'app.db').read_bytes(), original)
        self.assertIn(external_key, read_registry()['runtimes'])
        self.assertIsNone(read_registry()['default_runtime'])

    def test_remove_core_refuses_active_workspace(self):
        from fue_core.platform.uninstall import remove_managed_runtimes
        from fue_core.platform.lifecycle import InstanceLock
        workspace = self.workspace('shared')
        register_workspace(workspace)
        runtime = self.runtime()
        write_json(Path(runtime['core_dir']).parent / 'runtime.json', runtime)
        register_runtime(runtime)
        with InstanceLock(workspace), self.assertRaises(RuntimeError):
            remove_managed_runtimes()
        self.assertTrue(Path(runtime['core_dir']).exists())

    def test_remove_core_refuses_missing_ownership_or_data_overlap(self):
        from fue_core.platform.uninstall import remove_managed_runtimes
        runtime = self.runtime()
        register_runtime(runtime)
        with self.assertRaises(ValueError):
            remove_managed_runtimes()
        write_json(Path(runtime['core_dir']).parent / 'runtime.json', runtime)
        workspace = self.workspace('runtime/data')
        register_workspace(workspace)
        with self.assertRaises(ValueError):
            remove_managed_runtimes()
        self.assertTrue((workspace / 'app.db').exists())

    def test_both_entry_points_resolve_same_workspace_and_runtime(self):
        workspace = self.workspace('shared')
        runtime = self.runtime()
        register_runtime(runtime)
        key = register_workspace(workspace)
        spec = importlib.util.spec_from_file_location('skill_launcher_test', REPO / 'fue-skill/scripts/fue.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        agent = module.registered_connection()
        studio = inspect_installation()
        self.assertEqual(agent['data_dir'], studio['workspaces'][0]['data_dir'])
        self.assertEqual(agent['python'], studio['runtime']['python'])
        self.assertEqual(select_workspace()['id'], key)
        self.assertEqual(studio['workspaces'][0]['knowledge_bases'], 1)
        from fue_core.platform.paths import data_dir
        self.assertEqual(data_dir(), workspace)
        self.assertEqual(module.registered_connection('missing', str(workspace))['data_dir'], str(workspace))

    def test_explicit_registration_does_not_change_existing_default(self):
        first = register_workspace(self.workspace('first'))
        second = register_workspace(self.workspace('second'))
        self.assertNotEqual(first, second)
        self.assertEqual(select_workspace()['id'], first)
        self.assertEqual(select_workspace(second)['id'], second)
        register_workspace(self.root / 'second', make_default=True)
        self.assertEqual(select_workspace()['id'], second)

    def test_missing_workspace_and_ambiguous_default_do_not_fall_back(self):
        root = self.workspace('first')
        key = register_workspace(root)
        (root / 'app.db').unlink()
        with self.assertRaises(ValueError): select_workspace()
        self.assertFalse((root / 'app.db').exists())
        register_workspace(self.workspace('second'))
        with edit_registry() as data: data['default_workspace'] = None
        with self.assertRaises(ValueError): select_workspace()
        self.assertEqual(len(read_registry()['workspaces']), 2)

    def test_damaged_registry_is_not_overwritten(self):
        registry_path().parent.mkdir()
        registry_path().write_text('{broken')
        with self.assertRaises(ValueError): register_workspace(self.workspace('first'))
        self.assertEqual(registry_path().read_text(), '{broken')

    def test_runtime_missing_or_incompatible_is_not_silently_replaced(self):
        runtime = self.runtime()
        register_runtime(runtime)
        Path(runtime['python']).unlink()
        with self.assertRaises(ValueError): select_runtime()
        Path(runtime['python']).write_text('')
        runtime['version'] = '3.0.0'
        register_runtime(runtime)
        with self.assertRaises(ValueError): select_runtime()

    def test_skill_repeat_install_and_explicit_update_preserve_configuration(self):
        source = self.root / 'source'
        source.mkdir()
        (source / 'SKILL.md').write_text('first')
        target = Path(install_skill(source, self.root / 'host'))
        (target / 'connection.json').write_text('{"local":"keep"}')
        self.assertEqual(install_skill(source, self.root / 'host'), str(target))
        (source / 'SKILL.md').write_text('second')
        with self.assertRaises(ValueError): install_skill(source, self.root / 'host')
        install_skill(source, self.root / 'host', update=True)
        self.assertEqual((target / 'connection.json').read_text(), '{"local":"keep"}')
        backups = list((self.root / 'host').glob('fue-skill-backup-*'))
        self.assertEqual((backups[0] / 'SKILL.md').read_text(), 'first')

    def test_workspace_upgrade_backup_and_future_version_refusal(self):
        root = self.workspace('legacy')
        original = (root / 'app.db').read_bytes()
        manifest = prepare_workspace(root)
        backups = list((root / 'backups').glob('*/app.db'))
        self.assertEqual(len(backups), 1)
        with closing(sqlite3.connect(backups[0])) as db:
            self.assertEqual(db.execute('SELECT name FROM knowledge_bases').fetchone()[0], 'Existing library')
        write_json(root / 'workspace.json', manifest)
        prepare_workspace(root)
        self.assertEqual(len(list((root / 'backups').glob('*/app.db'))), 1)
        manifest['last_core_version'] = '3.0.0'
        write_json(root / 'workspace.json', manifest)
        with self.assertRaises(ValueError): prepare_workspace(root)
        self.assertEqual((root / 'app.db').read_bytes(), original)

    def test_legacy_desktop_hint_is_detected_without_creating_a_new_library(self):
        root = self.workspace('legacy-custom')
        write_json(self.root / 'config/core-connection.json', {'data_dir':str(root)})
        candidates = inspect_installation()['candidates']
        self.assertEqual([c['data_dir'] for c in candidates], [str(root)])
        self.assertFalse(registry_path().exists())

    def test_failed_runtime_upgrade_preserves_default_and_workspace(self):
        runtime = self.runtime()
        key = register_runtime(runtime)
        workspace = self.workspace('existing')
        register_workspace(workspace)
        original = (workspace / 'app.db').read_bytes()
        with self.assertRaises(FileNotFoundError):
            provision(self.root / 'missing-source', install_root=self.root / 'managed', upgrade=True)
        self.assertEqual(select_runtime()['id'], key)
        self.assertEqual((workspace / 'app.db').read_bytes(), original)
        self.assertEqual(list((self.root / 'managed').iterdir()), [])


if __name__ == '__main__': unittest.main()
