#!/usr/bin/env python3
"""Executable catalogue policy contract using real SDK archives, no live downloads."""
import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("store", ROOT / "tools/store.py")
store = importlib.util.module_from_spec(spec)
spec.loader.exec_module(store)


class AppleStorePolicy(unittest.TestCase):
    def test_validation_bump_and_site_preserve_curated_exclusion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "providers").mkdir()
            (root / "official.txt").write_text("spool.test\n")
            source = root / "source"
            (source / "logic").mkdir(parents=True)
            (source / "logic/provider.mjs").write_text("export function createSource() { return { describe: () => ({}) }; }\n")
            manifest = {"format": 2, "api": "0.2", "id": "spool.test", "name": "Policy test", "version": "1.0.0", "entry": "logic/provider.mjs"}
            (source / "manifest.json").write_text(json.dumps(manifest))
            first = store.sdk.build(source, root / "first.tar.zst")
            entry = store.sdk.feed(first, "https://releases.example/first.tar.zst")
            entry.update(appleAppStore=False, feed="https://releases.example/feed.json")
            manifest["version"] = "1.1.0"
            (source / "manifest.json").write_text(json.dumps(manifest))
            second = store.sdk.build(source, root / "second.tar.zst")
            latest = store.sdk.feed(second, "https://releases.example/second.tar.zst")
            latest["appleAppStore"] = True  # A provider feed cannot override curator policy.
            payloads = {entry["url"]: first.read_bytes(), latest["url"]: second.read_bytes(), entry["feed"]: json.dumps(latest).encode()}
            with patch.object(store, "ROOT", root), patch.object(store, "fetch", side_effect=lambda url, limit: payloads[url]) as fetch:
                for value in (None, "false", 0, 1):
                    invalid = dict(entry)
                    if value is None:
                        invalid.pop("appleAppStore")
                    else:
                        invalid["appleAppStore"] = value
                    with self.subTest(value=value), self.assertRaises(SystemExit):
                        store.check_entry(invalid, "spool.test")
                fetch.assert_not_called()
                store.check_entry(entry, "spool.test")
                path = root / "providers/spool.test.json"
                path.write_text(json.dumps(entry))
                store.bump()
                updated = json.loads(path.read_text())
                self.assertEqual(updated["version"], "1.1.0")
                self.assertIs(updated["appleAppStore"], False)
                self.assertEqual(updated["feed"], entry["feed"])
                store.site(root / "site")
                for name in ("official.json", "index.json"):
                    rows = json.loads((root / "site" / name).read_text())["providers"]
                    self.assertIs(rows[0]["appleAppStore"], False)


if __name__ == "__main__":
    unittest.main()
