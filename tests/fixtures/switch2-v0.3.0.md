RetroArch 1.22.2 for Nintendo Switch 2, built with libounce (ounce-devkit 20261115b, kaiHEN), Vulkan by default.

## What's new since v0.2.2

- **bsnes added, with MSU-1.** bsnes (libretro's bsnes v115) is now in the release as `bsnes_libretro_libnx.nro`. It plays MSU-1 games and hacks with their CD-quality soundtracks. See "MSU-1 with bsnes" below for how to lay out the files.
- **Faster Nintendo 64.** Mupen64Plus-Next's ParaLLEl-RDP hands its commands to the GPU thread through a lock-free ring, which cut that per-frame cost in Paper Mario from about 8.6 ms to about 1.9 ms. Its dynarec also sends about 25% fewer code-publish calls during scene changes.
- **ounce-devkit 20261115b.** Every core and the frontend are rebuilt from scratch on it. Its OunceVK fixes how the Vulkan driver frees and reuses GPU memory, and it now waits out slow GPU service calls instead of giving up.

## Install

Unzip `retroarch-switch2-v0.3.0.zip` to the root of the SD card, replacing the files from an earlier version. It's a complete drop-in and needs nothing else installed first. It contains:

- `switch/retroarch/retroarch_switch.nro`: the frontend
- `retroarch/cores/*_libretro_libnx.nro`: 23 cores, one NRO each (RetroArch with the core built in)
- `retroarch/assets`: the menu assets (Ozone, XMB, RGUI, GLUI, sounds)
- `retroarch/info`: core info files
- `retroarch/database/rdb`: the databases that playlist scanning uses

No `retroarch.cfg` is included, so an existing config is kept. On a fresh card RetroArch starts on Vulkan with threaded video and audio rate control off.

Launch RetroArch from hbmenu. If an older config has `video_driver = "gl"`, switch it to `vulkan` under Settings > Drivers.

## MSU-1 with bsnes

Keep the ROM and its MSU-1 files loose in the same folder, all with the ROM's base name:

```
Game.sfc      (or .smc)
Game.msu      MSU-1 data
Game-1.pcm    soundtrack
Game-2.pcm
...
```

Load the `.sfc` with bsnes. The ROM must not be zipped: RetroArch would unpack it to a temporary folder, where bsnes can't find the MSU-1 files.

## Cores

**Played and working**

| Core | System | Tested with |
|---|---|---|
| FCEUmm | NES | Super Mario Bros. 3 |
| Mesen | NES | Super Mario Bros. 3 |
| Snes9x 2010 | SNES | Star Fox, Yoshi's Island, Super Mario RPG |
| bsnes | SNES | An MSU-1 game with its soundtrack |
| mGBA | Game Boy Advance | The Minish Cap, from a fresh install |
| Genesis Plus GX | Mega Drive / Master System | Vectorman, OutRun, Golden Axe, Dragon Crystal |
| PicoDrive | Mega Drive / 32X | Vectorman; Metal Head (32X) at full speed |
| Beetle PCE Fast | PC Engine | Knight Rider Special |
| PCSX ReARMed | PlayStation | Gran Turismo (races included), Metal Gear Solid |
| Mupen64Plus-Next | Nintendo 64 | Paper Mario |
| Flycast | Dreamcast | Sonic Adventure, Phantasy Star Online Ver. 2 |

**Boots, not played yet:** VBA Next (Minish Cap), Beetle SuperGrafx (Knight Rider Special).

**Built, not tested yet:** Snes9x, Nestopia, QuickNES, Gambatte, Gearboy, SameBoy, Gearsystem, Handy, ProSystem, Stella.

## Notes

- **Shaders:** Vulkan uses slang presets (`.slangp`), which aren't included. GLSL shaders only apply to the `gl` driver.
- **BIOS:** PCSX ReARMed uses its built-in HLE BIOS when there's no real one in `/retroarch/cores/system`. PC Engine CD games need `syscard3.pce`.
- **N64 video:** ParaLLEl-RDP on Vulkan is the default. GLideN64 needs `video_driver = "gl"` for this core, in `/retroarch/config/Mupen64Plus-Next/Mupen64Plus-Next.cfg`.
- **Controller profiles:** on a fresh install RetroArch offers to download them. It's safe to accept, but it adds nothing: the Switch joypad driver has its controls built in.
- **Checksums:** `SHA256SUMS.txt` lists the zip and every NRO in it.
