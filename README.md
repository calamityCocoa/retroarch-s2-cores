# retroarch-s2-cores

An unofficial drop-in core mirror for RetroArch on Switch 2. Not affiliated with NerdsMcGee or libretro. It verifies upstream release checksums and republishes selected, **unmodified core binaries** in the flat format RetroArch's built-in updater expects. It never publishes the frontend.

## Console setup

In **RetroArch → Settings → Network → Buildbot Cores URL**, replace:

```
http://buildbot.libretro.com/nightly/nintendo/switch/libnx/latest
```

with your deployed mirror URL:

```
https://<username>.github.io/retroarch-s2-cores
```

A trailing slash also works. **Online Updater → Core Downloader / Update Installed Cores** then work normally. To revert, restore the default URL above (or clear the setting). No other console configuration changes are needed. There is no official Switch 2 buildbot path.

## Set up GitHub Pages

1. Put this repository's files into a GitHub repository named `retroarch-s2-cores`.
2. Select **Settings → Pages → Source: GitHub Actions**.
3. Enable Actions, then run **Actions → Mirror Switch 2 cores → Run workflow**. The workflow uses only the built-in `GITHUB_TOKEN`; no extra secrets are needed. Repository policy must allow `contents: write`, `pages: write`, and `id-token: write`.
4. Use the Pages URL shown by GitHub on the console. The default is `https://<username>.github.io/retroarch-s2-cores`. For a custom domain, set `MIRROR_SITE_URL` on the build step so metadata and idempotency use that URL; final verification uses the deployed URL returned by Pages.

**Why GitHub Actions instead of “Deploy from a branch → gh-pages / (root)”?** GitHub documents that [commits pushed using `GITHUB_TOKEN` do not trigger a Pages build](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site). To make unattended publication work without extra secrets, this workflow uses official Pages artifact deployment and its required `pages: write` and `id-token: write` permissions. It still force-pushes the complete flat site as a single root commit to `gh-pages`, as a branch mirror. The artifact contains the same files, including `.index-extended`. Do not configure branch publishing for this workflow.

The workflow checks every six hours at minute 17, and supports manual inputs:

- `force`: rebuild a tag already in the live `mirror.json`.
- `tag`: a specific upstream tag, such as `switch2-v0.3.0`; blank uses the latest stable release. Drafts and prereleases are ignored.
- `include_tiers`: defaults to `working,boots`. Set `working` for only played cores, or `working,boots,untested` for all classified tiers. Check `force` when changing tiers for an already mirrored tag. Scheduled runs use the default in the workflow; edit that default to change the standing selection.

The real release body's “Played and working” table supplies the working tier; the boots and untested lists supply the others. Names are matched using bundled `.info` corenames and core basenames. Unmatched names and cores are reported in the console, metadata, and Actions summary. If the working table disappears, **all cores are published**, with a prominent warning in the metadata, summary, and web page. A parsed table that yields no selected cores fails instead of silently publishing an empty mirror.

## Local usage

Python **3.11 or later**, Git for deployment, and pytest for tests. The script itself uses only the Python standard library.

```sh
python -m pip install pytest==8.3.5
python -m pytest -q
python mirror.py --dry-run --tag switch2-v0.3.0
```

This creates `site/` without deploying. Dry runs always build, even if the live site already has the tag. Use a fresh output folder on subsequent builds:

```sh
python mirror.py --dry-run --tag switch2-v0.3.0 --include-tiers working,boots,untested --output site-all
```

Set `GITHUB_TOKEN` in your environment to authenticate API requests and avoid anonymous rate limits; it is optional for a local public-release build. Do not commit tokens. A download needs several hundred MB and extraction needs additional disk space. Existing nonempty output folders are rejected to avoid mixing old and new files.

For automated publication, trigger the included workflow. Its Python build phase replaces the entire `gh-pages` branch with one root commit; the pinned official Pages actions upload and publish the site. Python then verifies the public index and one core archive for up to five minutes. Both slash forms are joined using RetroArch's convention. The live index must exactly match the build, and the downloaded core archive must match its SHA256. A network error or mismatch fails the run. An unchanged tag exits successfully without deploying; use `--force` to rebuild or recheck a failed deployment.

The workflow uses `--defer-live-check` to postpone verification until Pages has deployed. `python mirror.py --verify-live --repo YOUR-USERNAME/retroarch-s2-cores` verifies an existing `site/` folder without downloading a release or pushing a branch. A direct non-dry invocation pushes the branch and verifies the site; it does not perform the official Pages artifact deployment, which runs in Actions.

## Published format and verification

The output is flat: `.index-extended`, one `<name>_libretro_libnx.nro.zip` per selected core, `.nojekyll`, `mirror.json`, `SHA256SUMS.txt`, and `index.html`. Each zip contains exactly its one NRO at the root. Index rows are `YYYY-MM-DD CRC32HEX FILENAME`, sorted by filename with LF endings and a final newline. The CRC is of the uncompressed NRO; a zero CRC fails the build. Dates use UTC.

The script verifies the upstream zip SHA256 and every NRO, including the frontend, against `SHA256SUMS.txt`. Missing checksums, missing listed NROs, mismatches, unsafe archive paths, duplicate entries, symlinks, or invalid core NRO magic fail the build. Upstream content is never executed or imported. Only NRO and info data are extracted. Checksums establish consistency with the release; they are not independent signatures of upstream authenticity.

Publication fails if a file exceeds 95,000,000 bytes or the site exceeds 900,000,000 bytes. Git history on `gh-pages` is replaced rather than accumulating binary versions; GitHub controls garbage collection of unreachable objects. Source history remains on the default branch. `SHA256SUMS.txt` covers every published file except itself. `.nojekyll` allows Pages to serve the dotfile index. GitHub Releases cannot host this index reliably because it renames dot-prefixed assets.

If GitHub Pages refuses to serve `.index-extended`, deploy the **same `site/` folder to Cloudflare Pages**, with no framework/build transformation, and use that site's HTTPS URL on the console. Confirm that `/.index-extended` returns the literal text rather than an HTML fallback. Cloudflare has its own hosting/file-size limits; check those before migrating. The included workflow deploys to GitHub Pages, not Cloudflare.

## Licensing and source

MIT in [LICENSE](LICENSE) covers **only this repository's own mirror scripts, tests, and accompanying documentation**, not redistributed cores. Core binaries are redistributed unmodified and retain their GPL or other upstream open-source licences. Consult upstream for individual licences and corresponding source, including submodules and build dependencies. Distributors remain responsible for satisfying applicable source-distribution obligations.

For the tested release, see [switch2-v0.3.0](https://github.com/NerdsMcGee/retroarch-s2/releases/tag/switch2-v0.3.0) and its [exact tagged source](https://github.com/NerdsMcGee/retroarch-s2/tree/switch2-v0.3.0). Every generated `mirror.json` and `index.html` links to the exact release and tagged source actually mirrored, including when another tag is selected. The release-body test fixture is upstream release documentation, retained solely to test parsing.
