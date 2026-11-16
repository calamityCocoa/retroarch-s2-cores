#!/usr/bin/env python3
"""Verify upstream release data and publish a flat RetroArch core mirror."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
import zipfile
import zlib

UPSTREAM = 'NerdsMcGee/retroarch-s2'
TIERS = ('working', 'boots', 'untested')
MAX_FILE = 95_000_000
MAX_SITE = 900_000_000


def download(url, target, *, auth=False, attempts=3, timeout=30):
    """Stream responses to disk; never send credentials to the public site."""
    headers = {'User-Agent': 'retroarch-s2-cores', 'Accept': 'application/vnd.github+json' if auth else '*/*'}
    if auth and os.environ.get('GITHUB_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GITHUB_TOKEN']
    for attempt in range(attempts):
        try:
            with urlopen(Request(url, headers=headers), timeout=timeout) as response:
                if response.status != 200:
                    raise RuntimeError(f'HTTP {response.status}: {url}')
                with open(target, 'wb') as out:
                    shutil.copyfileobj(response, out, 1024 * 1024)
            return
        except HTTPError as exc:
            if exc.code == 404 or attempt == attempts - 1:
                raise
        except (URLError, TimeoutError, OSError):
            if attempt == attempts - 1:
                raise
        time.sleep(2 ** attempt)


def sha256(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def safe_path(name):
    if '\\' in name or re.match(r'^[A-Za-z]:', name):
        raise ValueError(f'Unsafe path: {name}')
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or not p.parts:
        raise ValueError(f'Unsafe path: {name}')
    return p.as_posix()


def parse_sums(text):
    result = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r'([a-fA-F0-9]{64})\s+\*?(.+)', line)
        if not match:
            raise ValueError(f'Invalid checksum line: {line}')
        name = safe_path(match[2])
        if name in result:
            raise ValueError(f'Duplicate checksum: {name}')
        result[name] = match[1].lower()
    return result


def verify_extract(archive, sums, destination):
    if sums.get(archive.name) != sha256(archive):
        raise ValueError('Release zip SHA256 mismatch or missing checksum')
    seen = set()
    with zipfile.ZipFile(archive) as zf:
        # Inspect every member, even ignored assets, before writing anything.
        for entry in zf.infolist():
            name = safe_path(entry.filename)
            if name in seen:
                raise ValueError(f'Duplicate archive path: {name}')
            seen.add(name)
            mode = entry.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError(f'Symlink in archive: {name}')
        total = 0
        for entry in zf.infolist():
            name = safe_path(entry.filename)
            if entry.is_dir():
                continue
            if not (name.lower().endswith('.nro') or (name.startswith('retroarch/info/') and name.endswith('.info'))):
                continue
            total += entry.file_size
            if total > 8_000_000_000:
                raise ValueError('Archive extraction exceeds 8 GB safety limit')
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(entry) as src, path.open('wb') as dst:
                shutil.copyfileobj(src, dst)
            if name.lower().endswith('.nro') and sums.get(name) != sha256(path):
                raise ValueError(f'NRO SHA256 mismatch or missing checksum: {name}')
    for name in sums:
        if name.lower().endswith('.nro') and name not in seen:
            raise ValueError(f'Checksummed NRO missing from archive: {name}')


def normalize(name):
    return re.sub(r'[^a-z0-9]', '', name.lower())


def parse_body(body):
    tiers = {tier: [] for tier in TIERS}
    lines = body.splitlines()
    table_found = False
    for i, line in enumerate(lines):
        if 'played and working' in line.lower():
            started = False
            for row in lines[i + 1:]:
                if not row.strip():
                    if started:
                        break
                    continue
                if '|' not in row:
                    break
                cells = [c.strip() for c in row.strip().strip('|').split('|')]
                if len(cells) < 3:
                    break
                started = True
                if cells[0].lower() == 'core':
                    table_found = True
                    continue
                if re.fullmatch(r'[:\- ]+', cells[0]):
                    continue
                tiers['working'].append(cells[0])
        clean = re.sub(r'[*`]', '', line).strip()
        for label, tier in [('Boots, not played yet:', 'boots'), ('Built, not tested yet:', 'untested')]:
            if clean.lower().startswith(label.lower()):
                names = re.sub(r'\([^)]*\)', '', clean[len(label):])
                tiers[tier].extend(n.strip().rstrip('.').strip() for n in names.split(',') if n.strip().rstrip('.').strip())
    return tiers, table_found


def classify(root, body):
    cores = sorted((root / 'retroarch/cores').glob('*_libretro_libnx.nro'))
    if not cores:
        raise ValueError('No cores found')
    mapping = {}
    def add(name, core):
        key = normalize(name)
        if key in mapping and mapping[key] != core.name:
            raise ValueError(f'Ambiguous core name: {name}')
        mapping[key] = core.name
    for core in cores:
        with core.open('rb') as stream:
            stream.seek(0x10)
            if stream.read(4) != b'NRO0':
                raise ValueError(f'Invalid NRO magic: {core.name}')
        add(core.name.removesuffix('_libretro_libnx.nro'), core)
        for info in (root / 'retroarch/info').glob('*.info'):
            if info.stem.removesuffix('_libnx') != core.stem.removesuffix('_libnx'):
                continue
            match = re.search(r'^\s*corename\s*=\s*"([^"]+)"', info.read_text(errors='replace'), re.M)
            if match:
                add(match[1], core)
    names, found = parse_body(body)
    assigned, unmatched = {}, []
    for tier in TIERS:
        for name in names[tier]:
            core = mapping.get(normalize(name))
            if core:
                assigned.setdefault(core, tier)
            else:
                unmatched.append(name)
    unclassified = [p.name for p in cores if p.name not in assigned]
    return cores, assigned, unmatched, unclassified, found


def package_core(core, output, date):
    crc = 0
    with core.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            crc = zlib.crc32(block, crc)
    if crc == 0:
        raise ValueError(f'Zero CRC32 cannot be published: {core.name}')
    filename = core.name + '.zip'
    with zipfile.ZipFile(output / filename, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(core, core.name)
    return f'{date} {crc:08x} {filename}\n', f'{crc:08x}'


def check_sizes(output):
    total = 0
    for path in output.iterdir():
        size = path.stat().st_size
        if size > MAX_FILE:
            raise ValueError(f'{path.name} exceeds the 95 MB file limit ({size} bytes)')
        total += size
    if total > MAX_SITE:
        raise ValueError(f'Site exceeds the 900 MB limit ({total} bytes)')


def build(root, output, release, archive_hash, include, site):
    cores, tiers, unmatched, unclassified, found = classify(root, release.get('body') or '')
    warnings = []
    if not found:
        warnings.append('WARNING: Played and working table not found; publishing ALL cores regardless of selected tiers.')
    chosen = [p for p in cores if not found or tiers.get(p.name) in include]
    if not chosen:
        raise ValueError('No cores selected; refusing to publish an empty mirror')
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('Output folder must be empty (use a new --output path)')
    now = datetime.now(timezone.utc)
    tag = release['tag_name']
    source = f'https://github.com/{UPSTREAM}/tree/{quote(tag, safe="")}'
    metadata = dict(upstream_tag=tag, upstream_release_url=release['html_url'], source_url=source,
                    zip_sha256=archive_hash, build_time=now.isoformat(), include_tiers=sorted(include),
                    notice='Redistributes unmodified binaries under their original GPL or other open-source licences. MIT covers mirror scripts only.',
                    warnings=warnings, unmatched_names=unmatched, unclassified_cores=unclassified, cores=[])
    lines = []
    for core in chosen:
        line, crc = package_core(core, output, now.strftime('%Y-%m-%d'))
        lines.append(line)
        metadata['cores'].append(dict(filename=core.name + '.zip', tier=tiers.get(core.name, 'unclassified'), crc32=crc))
    (output / '.index-extended').write_text(''.join(sorted(lines, key=lambda x: x.split()[2])), encoding='utf-8', newline='\n')
    (output / '.nojekyll').touch()
    (output / 'mirror.json').write_text(json.dumps(metadata, indent=2) + '\n')
    esc = html.escape
    rows = ''.join(f'<tr><td>{esc(c["filename"])}</td><td>{c["tier"]}</td></tr>' for c in metadata['cores'])
    (output / 'index.html').write_text(f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Switch 2 core mirror</title>
<h1>Unofficial RetroArch Switch 2 core mirror</h1><p>Not affiliated with NerdsMcGee or libretro.</p>
<p>Upstream release: <a href="{esc(release['html_url'], quote=True)}">{esc(tag)}</a> · <a href="{esc(source, quote=True)}">Exact upstream source</a></p>
{''.join('<p><strong>' + esc(w) + '</strong></p>' for w in warnings)}
<p>Buildbot Cores URL: <code>{esc(site)}</code> (with or without a trailing slash).</p>
<table><tr><th>Core archive</th><th>Tier</th></tr>{rows}</table>
<p>{esc(metadata['notice'])} See the upstream source for applicable licences and corresponding source.</p></html>\n''')
    (output / 'SHA256SUMS.txt').write_text(''.join(f'{sha256(p)}  {p.name}\n' for p in sorted(output.iterdir()) if p.is_file()))
    check_sizes(output)
    return metadata


def summary(metadata):
    counts = Counter(c['tier'] for c in metadata['cores'])
    message = '\n'.join([f'Upstream: {metadata["upstream_tag"]}', f'Published per tier: {dict(counts)}',
                         f'Unmatched names: {metadata["unmatched_names"]}', f'Unclassified NROs: {metadata["unclassified_cores"]}', *metadata['warnings']])
    print(message)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
            stream.write(message + '\n')


def deploy(output, repo):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        raise ValueError('Invalid GitHub repository')
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        raise ValueError('GITHUB_TOKEN is required for deployment')
    import base64
    env = os.environ.copy()
    env.update(GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='http.https://github.com/.extraheader',
               GIT_CONFIG_VALUE_0='AUTHORIZATION: basic ' + base64.b64encode(('x-access-token:' + token).encode()).decode())
    with tempfile.TemporaryDirectory() as temp:
        shutil.copytree(output, temp, dirs_exist_ok=True)
        def git(*args):
            subprocess.run(['git', *args], cwd=temp, env=env, check=True, stdout=subprocess.DEVNULL)
        git('init', '--initial-branch=gh-pages')
        git('config', 'user.name', 'github-actions[bot]')
        git('config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com')
        git('add', '--all')
        git('commit', '-m', 'Publish verified Switch 2 cores')
        git('push', '--force', f'https://github.com/{repo}.git', 'HEAD:refs/heads/gh-pages')


def verify_live(site, output, seconds=300):
    expected = (output / '.index-extended').read_bytes()
    core = expected.decode().splitlines()[0].split()[2]
    deadline = time.monotonic() + seconds
    error = None
    with tempfile.TemporaryDirectory() as temp:
        target = Path(temp) / 'response'
        while time.monotonic() < deadline:
            try:
                for base in (site.rstrip('/'), site.rstrip('/') + '/'):
                    for name in ('.index-extended', core):
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError('Live verification deadline exceeded')
                        download(base.rstrip('/') + '/' + name, target, attempts=1, timeout=min(20, remaining))
                        if name == '.index-extended':
                            if target.read_bytes() != expected:
                                raise ValueError('Live index does not match the build')
                        elif sha256(target) != sha256(output / core):
                            raise ValueError('Live core archive does not match the build')
                print('Live verification passed for both base URL forms')
                return
            except (HTTPError, URLError, OSError, ValueError, RuntimeError) as exc:
                error = exc
                time.sleep(max(0, min(10, deadline - time.monotonic())))
    raise RuntimeError(f'Live verification failed after {seconds}s: {error}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', default=os.environ.get('INPUT_TAG', ''))
    parser.add_argument('--force', action='store_true', default=os.environ.get('INPUT_FORCE') == 'true')
    parser.add_argument('--include-tiers', default=os.environ.get('INPUT_TIERS') or 'working,boots')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('site'))
    parser.add_argument('--repo', default=os.environ.get('GITHUB_REPOSITORY', ''))
    parser.add_argument('--site-url', default=os.environ.get('MIRROR_SITE_URL') or None)
    parser.add_argument('--defer-live-check', action='store_true', help='Push branch; workflow deploys Pages before verification')
    parser.add_argument('--verify-live', action='store_true', help='Verify an existing output folder against the public site only')
    args = parser.parse_args()
    include = set(args.include_tiers.split(','))
    if not include or not include <= set(TIERS):
        parser.error('--include-tiers must contain comma-separated working,boots,untested')
    site = args.site_url or (f'https://{args.repo.split("/")[0]}.github.io/{args.repo.split("/")[-1]}' if args.repo else 'https://<username>.github.io/retroarch-s2-cores')
    if not args.dry_run and not args.repo:
        parser.error('--repo is required for deployment; use --dry-run for a local build')
    if args.verify_live:
        verify_live(site, args.output)
        return
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        endpoint = 'tags/' + quote(args.tag, safe='') if args.tag else 'latest'
        download(f'https://api.github.com/repos/{UPSTREAM}/releases/{endpoint}', work / 'release.json', auth=True)
        release = json.loads((work / 'release.json').read_text())
        if release.get('draft') or release.get('prerelease'):
            print('Ignoring draft or prerelease')
            return
        # Dry runs always build so they provide a useful local artifact.
        if not args.force and not args.dry_run:
            try:
                download(site.rstrip('/') + '/mirror.json', work / 'live.json')
                live = json.loads((work / 'live.json').read_text())
                if live.get('upstream_tag') == release['tag_name']:
                    print('already up to date')
                    if os.environ.get('GITHUB_STEP_SUMMARY'):
                        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
                            stream.write(f'{release["tag_name"]}: already up to date\n')
                    return
            except HTTPError as exc:
                if exc.code != 404:
                    raise
        version = release['tag_name'].removeprefix('switch2-')
        zipname = f'retroarch-switch2-{version}.zip'
        assets = {a['name']: a['browser_download_url'] for a in release['assets']}
        for name in (zipname, 'SHA256SUMS.txt'):
            if name not in assets:
                raise ValueError(f'Required release asset missing: {name}')
            print(f'Downloading {name}', flush=True)
            download(assets[name], work / name)
        sums = parse_sums((work / 'SHA256SUMS.txt').read_text())
        verify_extract(work / zipname, sums, work / 'extracted')
        metadata = build(work / 'extracted', args.output, release, sha256(work / zipname), include, site)
        summary(metadata)
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
                stream.write('built=true\n')
        if not args.dry_run:
            deploy(args.output, args.repo)
            if not args.defer_live_check:
                verify_live(site, args.output)


if __name__ == '__main__':
    main()
