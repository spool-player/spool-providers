# Spool providers

The catalogue Spool installs providers from. Spool reads two files from this repository's GitHub Pages
site, <https://spool-player.github.io/spool-providers/>:

- `official.json`: first-party providers, checked at every launch
- `index.json`: everything, read when someone browses community providers or has one installed

Each entry names one release of one provider: its version, the archive's URL and its SHA-256. Spool
installs a download only when it matches, so what you get is exactly what was reviewed here.

The official catalogue includes Jellyfin, Emby, Plex and Stremio. Each provider keeps its
protocol and screens in its own repository under `spool-player`. Jellyfin, Emby and Plex
are MPL-2.0; the new Stremio provider is original 0BSD code, with no bundled torrent engine.

## Publishing a provider

1. Build and release your provider (see the SDK in
   [spool-player/spool](https://github.com/spool-player/spool/tree/main/sdk), or start from
   [spool-provider-example](https://github.com/spool-player/spool-provider-example)). Each release
   carries the `.tar.zst` package and its `spool-provider.json`:

   ```
   python3 sdk/spool-provider.py build .
   python3 sdk/spool-provider.py feed dist/<id>-<version>.tar.zst --url <where the release serves it>
   ```

2. Open a pull request here adding `providers/<id>.json` with that `spool-provider.json` and
   the required curated boolean `appleAppStore`. Existing reviewed providers are `true`;
   Stremio is `false` and is excluded from Apple App Store builds. The flag is catalogue policy,
   not provider-controlled feed metadata: release bumps preserve it, and both generated
   catalogues include it unchanged. App Store consumers include only explicit `true`.
   The check downloads the package, compares it with the entry and runs the validation Spool runs
   before installing. A maintainer reviews the code.

3. For each new version, open a pull request updating the same file.

Until then, anyone can already install it in Spool from a link to its repository (Settings →
Providers → Add from a link), and it will be kept up to date from its releases.

Ids starting with `spool.` are reserved for first-party providers, listed in `official.txt`. Those
follow their own releases: a scheduled job (and each first-party release, through
`repository_dispatch`) moves their entries to the latest verified release.

## Maintaining

```
python3 tools/store.py check            # every entry: download, verify, validate
python3 tools/store.py bump             # first-party entries to their latest releases
python3 tools/store.py site _site       # what Pages serves
```

`sdk/spool-provider.py` is Spool's own validator, copied from spool-player/spool at the revision in
`sdk/REVISION`. Needs Python 3.14 or the `zstd` command.

## Format-3 cutover staging

The validator and generated feed schema now require numeric `format: 3`, with no
`api` field. Existing curated entries retain `format: 2` because their URLs and
digests still name the actual published format-2 archives; they are intentionally
not valid cutover releases. Do not deploy this staged catalogue before replacing
all five entries with real format-3 release metadata.

Push the approved SDK source revision first, then validate and release each
canonical provider. Generate `spool-provider.json` from its actual uploaded
`.tar.zst` using the SDK `feed` command above. Replace each curated entry with
that output while preserving its reviewed `appleAppStore` flag (Stremio remains
false); only then run `store.py check` and regenerate/deploy the catalogue. The
host bundled-provider lock must likewise use the actual release archive bytes.
