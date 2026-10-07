#!/usr/bin/env python3
"""The Spool provider store.

  store.py check [providers/<id>.json ...]   download, verify and validate entries (all by default)
  store.py bump                              move first-party entries to their feeds' latest releases
  store.py site OUT                          write OUT/official.json, OUT/index.json and OUT/icons/

An entry is the feed entry a provider publishes with each release
(spool-provider.py feed): id, name, version, format, url, size, sha256 and
optionally summary, publisher and homepage. First-party entries
(official.txt) also name the `feed` they are kept current from.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import re
import sys
import tempfile
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("spool_provider", ROOT / "sdk/spool-provider.py")
sdk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sdk)

REQUIRED = ("id", "name", "version", "format", "url", "size", "sha256", "appleAppStore")
OPTIONAL = ("summary", "publisher", "homepage", "feed")
LISTED = REQUIRED + ("summary", "publisher", "homepage")
ICON_TYPES = {".svg": "image/svg+xml", ".png": "image/png"}


def fail(message: str):
    raise SystemExit(f"store: {message}")


def official() -> set[str]:
    lines = (ROOT / "official.txt").read_text().splitlines()
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def entries() -> dict[str, dict]:
    return {path.stem: json.loads(path.read_text()) for path in sorted((ROOT / "providers").glob("*.json"))}


def fetch(url: str, limit: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "spool-providers"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        fail(f"{url} is larger than {limit} bytes")
    return data


def version_key(version: str):
    core, _, pre = version.partition("-")
    return [int(part) for part in core.split(".")], pre == "", pre


def check_entry(entry: dict, name: str | None = None) -> tuple[dict, dict[str, bytes]]:
    """Validates the entry itself, then the package it points at."""
    missing = [key for key in REQUIRED if key not in entry]
    unknown = [key for key in entry if key not in REQUIRED + OPTIONAL]
    if missing or unknown:
        fail(f"{name or entry.get('id')}: missing {missing}, unknown {unknown}")
    if name is not None and name != entry["id"]:
        fail(f"providers/{name}.json holds {entry['id']}; name the file after the id")
    if type(entry["appleAppStore"]) is not bool:
        fail(f"{entry['id']}: appleAppStore must be a boolean")
    if entry["id"].startswith("spool.") and entry["id"] not in official():
        fail(f"{entry['id']}: the spool. prefix is for first-party providers")
    if type(entry["format"]) is not int or entry["format"] != 3:
        fail(f"{entry['id']}: package format must be 3")
    if not re.fullmatch(r"https://[^\s]+\.tar\.zst", entry["url"]):
        fail(f"{entry['id']}: url must be an https link to a .tar.zst")
    if not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
        fail(f"{entry['id']}: sha256 must be 64 lowercase hex digits")
    archive = fetch(entry["url"], sdk.MAX_ARCHIVE)
    if len(archive) != entry["size"] or hashlib.sha256(archive).hexdigest() != entry["sha256"]:
        fail(f"{entry['id']}: the download does not match its size and sha256")
    with tempfile.NamedTemporaryFile(suffix=".tar.zst") as file:
        file.write(archive)
        file.flush()
        manifest, files = sdk.read(pathlib.Path(file.name))
    for key in ("id", "name", "version", "format"):
        if manifest.get(key) != entry[key]:
            fail(f"{entry['id']}: entry {key} {entry[key]!r} differs from the package's {manifest.get(key)!r}")
    return manifest, files


def check(paths: list[str]) -> None:
    known = entries()
    targets = [pathlib.Path(path).stem for path in paths] if paths else list(known)
    for name in targets:
        if name not in known:
            print(f"{name}: removed")
            continue
        manifest, _ = check_entry(known[name], name)
        print(f"{name} {manifest['version']} ok")


def bump() -> None:
    for name, entry in entries().items():
        if name not in official() or not entry.get("feed"):
            continue
        latest = json.loads(fetch(entry["feed"], 64 * 1024))
        if version_key(latest.get("version", "0")) <= version_key(entry["version"]):
            continue
        latest = {key: latest[key] for key in REQUIRED + OPTIONAL if key in latest}
        latest["feed"] = entry["feed"]
        # Store inclusion is curated policy, never controlled by a provider feed.
        latest["appleAppStore"] = entry["appleAppStore"]
        check_entry(latest, name)
        (ROOT / "providers" / f"{name}.json").write_text(json.dumps(latest, indent=2) + "\n")
        print(f"{name} {entry['version']} -> {latest['version']}")


def site(out: pathlib.Path) -> None:
    first_party = official()
    (out / "icons").mkdir(parents=True, exist_ok=True)
    listed = []
    for name, entry in entries().items():
        manifest, files = check_entry(entry, name)
        row = {key: entry[key] for key in LISTED if key in entry}
        row["official"] = name in first_party
        icon = manifest.get("icon", "")
        suffix = pathlib.PurePosixPath(icon).suffix.lower()
        if icon in files and suffix in ICON_TYPES:
            (out / "icons" / f"{name}{suffix}").write_bytes(files[icon])
            row["icon"] = f"icons/{name}{suffix}"
        listed.append(row)
    listed.sort(key=lambda row: (not row["official"], row["name"].casefold()))
    write = lambda file, rows: (out / file).write_text(json.dumps({"format": 1, "providers": rows}, indent=2) + "\n")
    write("index.json", listed)
    write("official.json", [row for row in listed if row["official"]])
    (out / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><title>Spool providers</title>"
        "<p>This is the catalogue Spool reads. See "
        "<a href=https://github.com/spool-player/spool-providers>spool-player/spool-providers</a>.\n")
    print(f"{len(listed)} providers, {sum(row['official'] for row in listed)} official")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("check", "bump", "site"):
        fail(__doc__ or "usage: store.py check|bump|site")
    if sys.argv[1] == "check":
        check(sys.argv[2:])
    elif sys.argv[1] == "bump":
        bump()
    else:
        if len(sys.argv) != 3:
            fail("site needs an output directory")
        site(pathlib.Path(sys.argv[2]))


if __name__ == "__main__":
    main()
