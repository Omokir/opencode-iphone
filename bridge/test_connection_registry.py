import json
import os
from pathlib import Path
import tempfile
import unittest
from connection_registry import ConnectionRegistry, RegistryConflict, declaration


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.registry = ConnectionRegistry(self.root / 'registry')
        self.project = self.root / 'client'
        self.project.mkdir()

    def test_persistence_and_default_deny(self):
        result = self.registry.change(0, 'add', 'docs', {'type': 'remote', 'url': 'https://example.com/mcp'})
        self.assertEqual(result['servers']['docs']['projects'], [])
        self.assertEqual(ConnectionRegistry(self.registry.root).read(), result)
        self.assertEqual((self.registry.root / 'connections.json').stat().st_mode & 0o777, 0o600)

    def test_grant_revoke_and_remove(self):
        self.registry.change(0, 'add', 'local', {'type': 'local', 'command': ['/nonexistent-never-executed']})
        granted = self.registry.change(1, 'grant', 'local', directory=str(self.project))
        self.assertEqual(granted['servers']['local']['projects'], [str(self.project)])
        revoked = self.registry.change(2, 'revoke', 'local', directory=str(self.project))
        self.assertEqual(revoked['servers']['local']['projects'], [])
        self.assertEqual(self.registry.change(3, 'remove', 'local')['servers'], {})

    def test_conflicting_writes_do_not_overwrite(self):
        self.registry.change(0, 'add', 'docs', {'type': 'remote', 'url': 'https://example.com/mcp'})
        before = self.registry.read()
        with self.assertRaises(RegistryConflict):
            self.registry.change(0, 'remove', 'docs')
        self.assertEqual(self.registry.read(), before)

    def test_no_embedded_credentials(self):
        invalid = [
            {'type': 'remote', 'url': 'https://user:secret@example.com/mcp'},
            {'type': 'remote', 'url': 'https://example.com/mcp?token=secret'},
            {'type': 'remote', 'url': 'http://example.com/mcp'},
            {'type': 'remote', 'url': 'https://example.com/mcp', 'headers': {'Authorization': 'secret'}},
            {'type': 'local', 'command': 'sh -c bad'},
            {'type': 'local', 'command': ['tool'], 'environment': {'API_KEY': 'secret'}},
        ]
        for config in invalid:
            with self.assertRaises(ValueError):
                declaration(config)
        self.assertEqual(declaration({'type': 'local', 'command': ['tool'], 'environment': {'API_KEY': '{env:API_KEY}'}})['environment'], {'API_KEY': '{env:API_KEY}'})

    def test_duplicate_preserves_grants(self):
        config = {'type': 'remote', 'url': 'https://example.com/mcp'}
        self.registry.change(0, 'add', 'docs', config)
        self.registry.change(1, 'grant', 'docs', directory=str(self.project))
        with self.assertRaises(ValueError):
            self.registry.change(2, 'add', 'docs', config)
        self.assertEqual(self.registry.read()['revision'], 2)

    def test_project_symlink_and_missing_rejected(self):
        self.registry.change(0, 'add', 'docs', {'type': 'remote', 'url': 'https://example.com/mcp'})
        alias = self.root / 'alias'; alias.symlink_to(self.project)
        for value in [str(alias), str(self.root / 'missing'), 'relative']:
            with self.assertRaises((ValueError, FileNotFoundError)):
                self.registry.change(1, 'grant', 'docs', directory=value)
        self.assertEqual(self.registry.read()['revision'], 1)

    def test_corruption_and_symlinks_preserved(self):
        self.registry.read()
        file = self.registry.root / 'connections.json'
        file.write_text('invalid'); file.chmod(0o600)
        with self.assertRaises(ValueError):
            self.registry.change(0, 'add', 'docs', {'type': 'remote', 'url': 'https://example.com/mcp'})
        self.assertEqual(file.read_text(), 'invalid')
        file.unlink(); outside = self.root / 'outside'; outside.write_text('do not overwrite')
        file.symlink_to(outside)
        with self.assertRaises(OSError):
            self.registry.read()
        self.assertEqual(outside.read_text(), 'do not overwrite')

    def test_nonprivate_directory_rejected(self):
        self.registry.root.mkdir(mode=0o755)
        self.registry.root.chmod(0o755)
        with self.assertRaises(ValueError):
            self.registry.read()


if __name__ == '__main__':
    unittest.main()
