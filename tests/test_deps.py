import contextlib
import io
import unittest
from unittest import mock

from mak_attatch.core import deps


class DepsDetectionTest(unittest.TestCase):
    def test_package_manager_apt(self):
        with mock.patch.object(deps, "distro_id", return_value="ubuntu"):
            self.assertEqual(deps.package_manager(), "apt")

    def test_package_manager_pacman(self):
        with mock.patch.object(deps, "distro_id", return_value="arch"):
            self.assertEqual(deps.package_manager(), "pacman")

    def test_package_manager_unknown(self):
        with mock.patch.object(deps, "distro_id", return_value="unknown"), \
             mock.patch.object(deps.shutil, "which", return_value=None):
            self.assertEqual(deps.package_manager(), "unknown")

    def test_install_command_apt(self):
        with mock.patch.object(deps, "package_manager", return_value="apt"):
            # Only the required tools by default; no third-party repo needed.
            self.assertEqual(deps.install_command(), "sudo apt install -y ffmpeg mkvtoolnix")
            self.assertEqual(deps.install_command(include_tui=True),
                             "sudo apt install -y ffmpeg mkvtoolnix yazi chafa")

    def test_install_command_pacman_uses_cli_package(self):
        with mock.patch.object(deps, "package_manager", return_value="pacman"):
            self.assertIn("mkvtoolnix-cli", deps.install_command())

    def test_install_command_unknown_empty(self):
        with mock.patch.object(deps, "package_manager", return_value="unknown"):
            self.assertEqual(deps.install_command(), "")

    def test_yazi_keyring_only_for_apt(self):
        with mock.patch.object(deps, "package_manager", return_value="apt"):
            cmds = deps.yazi_keyring_commands()
            self.assertIn("yazi-keyring.gpg", cmds[1])
            # A failed or empty download must stop before the source is added.
            self.assertIn("test -s", cmds[1])
            self.assertEqual(cmds[-1], "sudo apt-get update")
        with mock.patch.object(deps, "package_manager", return_value="pacman"):
            self.assertEqual(deps.yazi_keyring_commands(), [])

    def test_yazi_copr_only_for_dnf(self):
        with mock.patch.object(deps, "package_manager", return_value="dnf"):
            cmds = deps.yazi_copr_commands()
            self.assertEqual(cmds, ["sudo dnf copr enable -y lihaohong/yazi"])
        with mock.patch.object(deps, "package_manager", return_value="apt"):
            self.assertEqual(deps.yazi_copr_commands(), [])

    def test_yazi_copr_cli(self):
        with mock.patch.object(deps, "package_manager", return_value="dnf"), \
             mock.patch.object(deps.sys, "argv", ["deps.py", "--yazi-copr"]), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(deps._main(), 0)
            self.assertIn("dnf copr enable -y lihaohong/yazi", out.getvalue())
        with mock.patch.object(deps, "package_manager", return_value="apt"), \
             mock.patch.object(deps.sys, "argv", ["deps.py", "--yazi-copr"]), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(deps._main(), 0)
            self.assertEqual(out.getvalue().strip(), "")

    def test_missing_binaries_filters_path(self):
        with mock.patch.object(
                deps.shutil, "which",
                side_effect=lambda b: None if b in ("yazi", "chafa")
                else "/usr/bin/" + b):
            self.assertEqual(deps.missing_binaries(), [])
            self.assertEqual(sorted(deps.missing_binaries(include_tui=True)), ["chafa", "yazi"])

    def test_hint_includes_install_command_and_keyring(self):
        with mock.patch.object(deps, "package_manager", return_value="apt"):
            hint = deps.hint(["yazi"])
            self.assertIn("sudo apt install -y", hint)
            self.assertIn("yazi-keyring.gpg", hint)

    def test_hint_includes_copr_for_dnf(self):
        with mock.patch.object(deps, "package_manager", return_value="dnf"):
            hint = deps.hint(["yazi"])
            self.assertIn("sudo dnf install -y", hint)
            self.assertIn("dnf copr enable -y lihaohong/yazi", hint)

    def test_hint_empty_when_no_missing(self):
        self.assertEqual(deps.hint([]), "")


if __name__ == "__main__":
    unittest.main()
