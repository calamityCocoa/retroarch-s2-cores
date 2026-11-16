import hashlib
import json
from pathlib import Path
import re
import zipfile
import zlib

import pytest
import mirror

BODY = (Path(__file__).parent / 'fixtures/switch2-v0.3.0.md').read_text()


def nro():
    return b'\0' * 16 + b'NRO0' + b'unmodified core data' * 50


def test_real_release_body():
    tiers, found = mirror.parse_body(BODY)
    assert found
    assert tiers['working'] == ['FCEUmm', 'Mesen', 'Snes9x 2010', 'bsnes', 'mGBA', 'Genesis Plus GX', 'PicoDrive', 'Beetle PCE Fast', 'PCSX ReARMed', 'Mupen64Plus-Next', 'Flycast']
    assert tiers['boots'] == ['VBA Next', 'Beetle SuperGrafx']
    assert tiers['untested'] == ['Snes9x', 'Nestopia', 'QuickNES', 'Gambatte', 'Gearboy', 'SameBoy', 'Gearsystem', 'Handy', 'ProSystem', 'Stella']


def test_missing_table():
    assert mirror.parse_body('## Cores\nNew format')[1] is False
    assert mirror.parse_body('Played and working\nNo table')[1] is False


def test_package_format_and_contents(tmp_path):
    core = tmp_path / 'mgba_libretro_libnx.nro'
    core.write_bytes(nro())
    line, crc = mirror.package_core(core, tmp_path, '2026-11-16')
    assert re.fullmatch(r'2026-11-16 [0-9a-f]{8} mgba_libretro_libnx\.nro\.zip\n', line)
    assert crc == f'{zlib.crc32(nro()):08x}'
    assert crc != '00000000'
    with zipfile.ZipFile(tmp_path / (core.name + '.zip')) as archive:
        assert archive.namelist() == [core.name]
        assert archive.read(core.name) == nro()
        assert archive.getinfo(core.name).compress_type == zipfile.ZIP_DEFLATED


def make_archive(tmp_path, entries):
    archive = tmp_path / 'release.zip'
    with zipfile.ZipFile(archive, 'w') as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    sums = {name: hashlib.sha256(data).hexdigest() for name, data in entries.items()}
    sums[archive.name] = mirror.sha256(archive)
    return archive, sums


@pytest.mark.parametrize('name', ['../evil.nro', '/evil.nro', 'C:/evil.nro', 'a/../../evil.nro', 'a\\evil.nro'])
def test_zip_slip(tmp_path, name):
    archive, sums = make_archive(tmp_path, {name: nro()})
    with pytest.raises(ValueError, match='Unsafe path'):
        mirror.verify_extract(archive, sums, tmp_path / 'out')


@pytest.mark.parametrize('failure', ['zip', 'missing', 'wrong', 'absent'])
def test_checksum_failures(tmp_path, failure):
    name = 'switch/retroarch/retroarch_switch.nro'
    archive, sums = make_archive(tmp_path, {name: nro()})
    if failure == 'zip':
        sums[archive.name] = '0' * 64
    elif failure == 'missing':
        del sums[name]
    elif failure == 'wrong':
        sums[name] = '0' * 64
    else:
        sums['absent.nro'] = '0' * 64
    with pytest.raises(ValueError):
        mirror.verify_extract(archive, sums, tmp_path / 'out')


def test_sums():
    value = 'a' * 64
    assert mirror.parse_sums(f'{value}  ./a.nro\n{value} *b.nro\n') == {'a.nro': value, 'b.nro': value}


def make_root(tmp_path):
    root = tmp_path / 'input'
    (root / 'retroarch/cores').mkdir(parents=True)
    (root / 'retroarch/info').mkdir()
    for name, title, suffix in [('mgba', 'mGBA', ''), ('vba_next', 'VBA Next', '_libnx'), ('other', 'Other', '')]:
        (root / f'retroarch/cores/{name}_libretro_libnx.nro').write_bytes(nro())
        (root / f'retroarch/info/{name}_libretro{suffix}.info').write_text(f'corename = "{title}"\n')
    return root


@pytest.mark.parametrize('fallback', [False, True])
def test_build(tmp_path, fallback):
    root = make_root(tmp_path)
    output = tmp_path / 'site'
    release = dict(tag_name='switch2-v0.3.0', html_url='https://github.com/NerdsMcGee/retroarch-s2/releases/tag/switch2-v0.3.0', body='changed' if fallback else BODY)
    metadata = mirror.build(root, output, release, 'a' * 64, {'working', 'boots'}, 'https://example.com/cores')
    assert len(metadata['cores']) == (3 if fallback else 2)
    assert bool(metadata['warnings']) is fallback
    assert 'other_libretro_libnx.nro' in metadata['unclassified_cores']
    assert metadata['source_url'].endswith('/tree/switch2-v0.3.0')
    index = (output / '.index-extended').read_bytes()
    assert index.endswith(b'\n') and b'\r' not in index
    names = [line.split()[2] for line in index.decode().splitlines()]
    assert names == sorted(names)
    for name in names:
        with zipfile.ZipFile(output / name) as zf:
            assert zf.namelist() == [name.removesuffix('.zip')]
    assert (output / '.nojekyll').read_bytes() == b''
    for name, digest in mirror.parse_sums((output / 'SHA256SUMS.txt').read_text()).items():
        assert mirror.sha256(output / name) == digest
    assert all(p.is_file() for p in output.iterdir())


def test_bad_magic(tmp_path):
    root = make_root(tmp_path)
    next((root / 'retroarch/cores').iterdir()).write_bytes(b'bad')
    with pytest.raises(ValueError, match='magic'):
        mirror.classify(root, BODY)


def test_size_limits(tmp_path, monkeypatch):
    (tmp_path / 'a').write_bytes(b'abcd')
    monkeypatch.setattr(mirror, 'MAX_FILE', 3)
    with pytest.raises(ValueError, match='95 MB'):
        mirror.check_sizes(tmp_path)
    monkeypatch.setattr(mirror, 'MAX_FILE', 5)
    monkeypatch.setattr(mirror, 'MAX_SITE', 3)
    with pytest.raises(ValueError, match='900 MB'):
        mirror.check_sizes(tmp_path)


def test_live_verification(tmp_path, monkeypatch):
    output = tmp_path / 'site'
    output.mkdir()
    (output / '.index-extended').write_text('2026-11-16 abcdef12 a.nro.zip\n')
    (output / 'a.nro.zip').write_bytes(b'zip bytes')
    requested = []
    def download(url, target, **kwargs):
        requested.append(url)
        target.write_bytes((output / url.rsplit('/', 1)[1]).read_bytes())
    monkeypatch.setattr(mirror, 'download', download)
    mirror.verify_live('https://example.com/mirror/', output, seconds=1)
    assert requested == ['https://example.com/mirror/.index-extended', 'https://example.com/mirror/a.nro.zip'] * 2


def test_zero_crc_rejected(tmp_path, monkeypatch):
    core = tmp_path / 'a_libretro_libnx.nro'
    core.write_bytes(nro())
    monkeypatch.setattr(mirror.zlib, 'crc32', lambda *args: 0)
    with pytest.raises(ValueError, match='Zero CRC32'):
        mirror.package_core(core, tmp_path, '2026-11-16')


def test_stale_live_index_fails(tmp_path, monkeypatch):
    (tmp_path / '.index-extended').write_text('2026-11-16 abcdef12 a.nro.zip\n')
    (tmp_path / 'a.nro.zip').write_bytes(b'zip')
    monkeypatch.setattr(mirror, 'download', lambda url, target, **kwargs: target.write_bytes(b'stale'))
    monkeypatch.setattr(mirror.time, 'sleep', lambda seconds: None)
    with pytest.raises(RuntimeError, match='Live index does not match'):
        mirror.verify_live('https://example.com', tmp_path, seconds=0.01)


def test_idempotency(tmp_path, monkeypatch, capsys):
    import sys
    monkeypatch.setattr(sys, 'argv', ['mirror.py', '--repo', 'owner/repo'])
    calls = []
    def download(url, target, **kwargs):
        calls.append(url)
        target.write_text(json.dumps({'tag_name': 'switch2-v0.3.0'} if 'api.github.com' in url else {'upstream_tag': 'switch2-v0.3.0'}))
    monkeypatch.setattr(mirror, 'download', download)
    mirror.main()
    assert len(calls) == 2
    assert 'already up to date' in capsys.readouterr().out


def test_verify_only_does_not_fetch_release(tmp_path, monkeypatch):
    import sys
    monkeypatch.setattr(sys, 'argv', ['mirror.py', '--verify-live', '--repo', 'owner/repo', '--output', str(tmp_path)])
    calls = []
    monkeypatch.setattr(mirror, 'verify_live', lambda site, output: calls.append((site, output)))
    monkeypatch.setattr(mirror, 'download', lambda *a, **kw: pytest.fail('verify-only fetched release data'))
    mirror.main()
    assert calls == [('https://owner.github.io/repo', tmp_path)]


def test_deploy_single_root_commit(tmp_path, monkeypatch):
    (tmp_path / '.index-extended').write_text('index')
    monkeypatch.setenv('GITHUB_TOKEN', 'test-token')
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        assert 'test-token' not in ' '.join(args)
        assert kwargs['check'] is True
        assert (Path(kwargs['cwd']) / '.index-extended').read_text() == 'index'
    monkeypatch.setattr(mirror.subprocess, 'run', run)
    mirror.deploy(tmp_path, 'owner/repo')
    assert calls[0] == ['git', 'init', '--initial-branch=gh-pages']
    assert sum('commit' in c for c in calls) == 1
    assert calls[-1] == ['git', 'push', '--force', 'https://github.com/owner/repo.git', 'HEAD:refs/heads/gh-pages']
