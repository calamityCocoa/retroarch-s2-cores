# Validation

Validated on 2026-11-16 using Python 3.14.10 and pytest 8.3.5.

- 23 pytest cases pass, including the actual upstream v0.3.0 release-body fixture, index/zip format, tier selection, fallback, NRO magic, checksum failures, path traversal, size limits, zero CRC rejection, idempotency and live-response validation.
- A real network dry run with `--tag switch2-v0.3.0` succeeded. The upstream archive and all contained NRO checksums passed.
- Published selection: 11 working + 2 boots = 13 cores; no unmatched release names or unclassified cores.
- Output size: 189,653,052 bytes. Largest file: `mupen64plus_next_libretro_libnx.nro.zip`, 16,813,894 bytes.
- Independently opened all 13 resulting core zips and checked each has exactly one root-level NRO and that its uncompressed CRC matches the index.
- The download/build output is not bundled with this source repository.

Published successfully to https://calamitycocoa.github.io/retroarch-s2-cores/ on 2026-11-16.

GitHub Actions run https://github.com/calamityCocoa/retroarch-s2-cores/actions/runs/43915897306 passed tests, build, branch push, Pages artifact deployment, and live verification. Independently downloaded all 13 public core archives, checked their single root-level NRO entries, and verified every uncompressed CRC against the public index. Public metadata reports switch2-v0.3.0 with no warnings.
