from pathlib import Path
import plistlib
import tempfile
import unittest

from terminal_policy import directory_path, paste_text, shell_path


class TerminalPolicyTests(unittest.TestCase):
    def test_project_path_is_data_not_a_shell_command(self):
        with tempfile.TemporaryDirectory() as root:
            project = Path(root) / 'project ; $(touch marker)'; project.mkdir()
            self.assertEqual(directory_path(str(project)), str(project))
            self.assertFalse((project/'marker').exists())
            for value in ('relative', str(project)+'\n', str(project)+'\u202e', '/path/that/does/not/exist'):
                with self.assertRaises((ValueError, OSError)):
                    directory_path(value)

    def test_symlink_resolution_is_explicit_and_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root)/'target'; target.mkdir()
            link = Path(root)/'link'; link.symlink_to(target)
            self.assertEqual(directory_path(str(link)), str(target))
            file = target/'file'; file.write_text('fixture')
            with self.assertRaises(ValueError):
                directory_path(str(file))

    def test_shell_is_an_installed_allowlisted_program_not_command_text(self):
        self.assertEqual(shell_path('/bin/sh'), '/bin/sh')
        for value in ('sh -c evil', '/tmp/user-program', '$(touch marker)'):
            with self.assertRaises(ValueError):
                shell_path(value)

    def test_paste_is_bounded_and_rejects_terminal_control_sequences(self):
        self.assertEqual(paste_text('printf "safe"\n\ttext'), 'printf "safe"\n\ttext')
        for value in (None, 'x'*65537, 'é'*32769, '\x1b]52;clipboard\x07', '\x00', '\x03', '\x7f', '\ud800', '\u202ehidden', '\ufeffhidden'):
            with self.assertRaises((ValueError, UnicodeError)):
                paste_text(value)

    def test_iphone_brand_keeps_existing_bundle_identity(self):
        path = Path(__file__).resolve().parent.parent/'ios/Info.plist'
        info = plistlib.loads(path.read_bytes())
        self.assertEqual(info['CFBundleDisplayName'], 'KzL Agent')
        self.assertEqual(info['CFBundleIdentifier'], 'com.omokir.opencodepocket')
        self.assertEqual(info['CFBundleExecutable'], 'OpenCodePocket')


if __name__ == '__main__':
    unittest.main()
