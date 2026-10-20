import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import config


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mak-config-"))
        for target, value in (
            ("CONFIG_DIR", self.tmp),
            ("CONFIG_FILE", self.tmp / "config.json"),
        ):
            patcher = mock.patch.object(config, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_defaults_when_missing(self):
        data = config.load()
        self.assertEqual(data["default_poster_size"], "w500")
        self.assertEqual(data["scan_api_delay"], 0.25)

    def test_load_normalizes_bad_values(self):
        config.CONFIG_FILE.write_text(json.dumps({
            "default_poster_size": "huge",
            "scan_api_delay": "nope",
            "auto_convert_video": "yes",
        }))
        data = config.load()
        self.assertEqual(data["default_poster_size"], "w500")
        self.assertEqual(data["scan_api_delay"], 0.25)
        self.assertIs(data["auto_convert_video"], True)

    def test_load_ignores_non_dict(self):
        config.CONFIG_FILE.write_text("[1, 2, 3]")
        self.assertEqual(config.load(), config.DEFAULTS.copy())

    def test_set_rejects_unknown_poster_size(self):
        with self.assertRaises(ValueError):
            config.set("default_poster_size", "huge")

    def test_set_clamps_negative_delay(self):
        config.set("scan_api_delay", "-5")
        self.assertEqual(config.get("scan_api_delay"), 0.0)

    def test_set_rejects_non_numeric_delay(self):
        with self.assertRaises(ValueError):
            config.set("scan_api_delay", "soon")

    def test_env_var_overrides_stored_key(self):
        config.set("tmdb_api_key", "stored-key-1234567890")
        with mock.patch.dict(os.environ, {config.API_KEY_ENV: "env-key-1234567890"}):
            self.assertEqual(config.get("tmdb_api_key"), "env-key-1234567890")

    def test_version_matches_package(self):
        self.assertEqual(config.VERSION, "1.3.5")


if __name__ == "__main__":
    unittest.main()
