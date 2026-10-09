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
    def test_https_packages_bump_and_site_preserve_curated_exclusion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "providers").mkdir()
            (root / "official.txt").write_text("spool.test\n")
            source = root / "source"
            (source / "logic").mkdir(parents=True)
            (source / "logic/provider.mjs").write_text("export function createSource() { return { describe: () => ({}) }; }\n")
            manifest = {"format": 3, "capabilities": [], "id": "spool.test", "name": "Policy test", "version": "1.0.0", "entry": "logic/provider.mjs"}
            (source / "manifest.json").write_text(json.dumps(manifest))
            first = store.sdk.build(source, root / "first.tar.zst")
            entry = store.sdk.feed(first, "https://releases.example/first.tar.zst")
            entry.update(appleAppStore=False, feed="https://releases.example/feed.json")
            manifest["version"] = "1.1.0"
            (source / "manifest.json").write_text(json.dumps(manifest))
            second = store.sdk.build(source, root / "second.tar.zst")
            latest = store.sdk.feed(second, "https://releases.example/second.szo")
            latest["appleAppStore"] = True  # A provider feed cannot override curator policy.
            payloads = {entry["url"]: first.read_bytes(), latest["url"]: second.read_bytes(), entry["feed"]: json.dumps(latest).encode()}
            package_urls = (
                entry["url"],
                "https://releases.example/first.szo",
                "https://releases.example/download/42?asset=package",
            )
            payloads.update({url: payloads[entry["url"]] for url in package_urls})
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
                for url in package_urls:
                    candidate = dict(entry, url=url)
                    with self.subTest(url=url):
                        checked, files = store.check_entry(candidate, "spool.test")
                        self.assertEqual(checked["version"], "1.0.0")
                        self.assertIn("logic/provider.mjs", files)
                fetch.reset_mock()
                for url in (
                    "http://releases.example/first.tar.zst",
                    "ftp://releases.example/first.tar.zst",
                    "file:///tmp/first.tar.zst",
                    "wss://releases.example/first.tar.zst",
                    "data:application/octet-stream;base64,eA==",
                ):
                    with self.subTest(url=url), self.assertRaisesRegex(SystemExit, "url must be an https link"):
                        store.check_entry(dict(entry, url=url), "spool.test")
                fetch.assert_not_called()
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
                    for key in ("url", "size", "sha256", "format"):
                        self.assertEqual(rows[0][key], latest[key])


if __name__ == "__main__":
    unittest.main()
