import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from install import install, digest


class InstallTests(unittest.TestCase):
    def test_install_reinstall_and_unknown_change_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            result = install(home)
            self.assertEqual(len(result['files']), 12)
            for path, expected in result['files'].items():
                self.assertEqual(digest(Path(path).read_bytes()), expected)
            self.assertEqual(result, install(home))
            launcher = home / '.local/bin/opencode-pocket'
            self.assertTrue(launcher.stat().st_mode & 0o100)
            self.assertTrue((home / '.local/bin/kzl-agent').stat().st_mode & 0o100)
            desktop = home / '.local/share/applications/com.omokir.PocketDesktop.desktop'
            self.assertIn('Name=KzL Agent\n', desktop.read_text())
            target = home / '.local/share/opencode-pocket-desktop/main.py'
            output = subprocess.check_output(['/usr/bin/python3', str(target), '--help'], text=True, timeout=10)
            self.assertIn('--portrait', output)
            target.write_text('user modification')
            with self.assertRaises(RuntimeError):
                install(home)
            self.assertEqual(target.read_text(), 'user modification')


if __name__ == '__main__':
    unittest.main()
