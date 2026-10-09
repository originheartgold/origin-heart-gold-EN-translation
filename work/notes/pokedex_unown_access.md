# Ruins of Alph map 491 access audit

Audited 2026-10-09, read-only against `work/rom/origin_v4.0.3_cn.nds` using the existing `emu_harness.MapGrid` collision parser and `romdata` script/event parsers. No ROM build, emulator-state modification or download.

**Conclusion: exclude map 491 as a normal-play encounter location.** Its exterior entry warps are moved onto blocked terrain by the ordinary map-load branch. The physically accessible coordinates belong to map 323 instead. This conclusion uses actual collision bytes, not the map's “unused Arceus copy” label.

## Actual terrain at relocated entrances

Map 113 (Ruins of Alph exterior), matrix 0, land permissions from `a/0/6/5`:

| Tile (x,z) | Behavior byte | Collision bit 15 | Meaning |
|---|---:|---|---|
| 418,284 | 0x00 | set | blocked terrain |
| 419,284 | 0x00 | set | blocked terrain |
| 430,284 | 0x6E | clear | accessible original doorway |
| 431,284 | 0x6E | clear | accessible original doorway |

The relocated tiles also sit in a continuous blocked band: x=412–429 at z=282–284 are blocked. These are not surfable water tiles or accessible hidden warp tiles. The original doorway at (430/431,284) is walkable.

Reproduction from repository root:

```python
import sys
sys.path.insert(0, 'work/tools')
from emu_harness import MapGrid, DEF_ROM_CN
g = MapGrid(DEF_ROM_CN, 113)
for point in [(418,284), (419,284), (430,284), (431,284)]:
    print(point, g.tile(*point))
```

Run with `.venv/bin/python`. Output respectively: `(0, True)`, `(0, True)`, `(110, False)`, `(110, False)`; tuple fields are behavior and blocked.

## Entry routing

Map113 event110 stores overlapping doorway warps: 8/9 → map323, 11/12 → map323, 13/14 → map491, all initially at (430/431,284).

File37 map-load branch at @1385 checks variable0x403E:

- At values below6: @1959/@1967 moves warps11/12 to (418/419,284), and @1975/@1983 moves map491 warps13/14 to the same blocked coordinates. Ordinary warps8/9 into map323 stay on the doorway.
- At value6: @1925–1949 moves warps8/9 and13/14 away, leaving11/12, still into map323.
- At value7 or greater: @1891–1915 moves warps8/9 and11/12 away, which would expose the map491 pair.

Thus **map491 requires 0x403E ≥ 7** to be normally entered from outside. The existing Unown-report progression finding D-1427 documents that the research progression cannot advance normally: `guide/13-dungeons-and-common.md` and `guide/known-issues.md` explain the unreachable report-note progression (0x40EC). A whole indexed-script search finds the only write to0x403E is file38 @2304 `AddVar [0x403E,1]` within that researcher-report advancement. No reachable independent setter bypasses it.

The separately identified scripted Warp491 at file49 @2762 belongs to unattached entry2, not an alternative player-accessible route. Map491's own exits lead to323 and do not provide an incoming path.

The terrain test therefore closes the remaining loophole: the hidden map491 doorway cannot be entered by walking onto its relocated coordinates, even if an encounter table exists there. The active Ruins of Alph chambers/maps must remain available; this exclusion applies specifically to map491 (and the separately reviewed inaccessible map490), not to the whole Ruins of Alph area.
