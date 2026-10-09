# Play order and where each text bank really appears

**Status (reviewed 2026-09-29): historical.** The play-order research (2026-09-28) behind `manifest_playorder.json` (R001–R069). All batches are done; "still untranslated" below describes that date. `build_playorder.py` was removed on 2026-10-09 (cleanup); `build_bank_maps.py` stays.

Status date: 2026-09-28. This note replaces the vanilla-name guesses in the `manifest.json` labels for scheduling purposes. `manifest.json` itself is unchanged.

## Why

A playtest found Chinese text in the player's house in Pallet Town: Mom giving the Running Shoes, and the Switch upstairs. Those strings are in banks 0537/0538. The manifest labelled them "New Bark" because in vanilla HGSS those maps are the New Bark player house (`MAP_NEW_BARK_PLAYER_HOUSE_1F/2F`, zones 63/64). The hack kept those maps but changed their location to **Pallet Town**. It rewires 54 of the 540 zones like this. B058–B059 have since translated 0537/0538 (all 310 strings are now draft).

(The rival's house is zone 504 `MAP_PALLET_TOWN_BLUES_HOUSE_1F`, bank **0442**, translated in B033. Bank 0527 is the Saffron Magnet Train station.)

## Files

| file | what |
|---|---|
| `work/translate/scripts/build_bank_maps.py` | Reads the hack ROM and writes `bank_maps.json` |
| `work/translate/bank_maps.json` | `{"NNNN": [{zone_id, kind, map_name_zh, map_name_en, vanilla_const, header{…}}]}`, plus `_zones` (all 540 headers with warps and overworld neighbours) and `_meta` |
| `work/translate/ref/hgss_map_constants.json` | pret zone constants (vanilla map names, e.g. `MAP_T20R0201`) |
| `work/translate/scripts/build_playorder.py` | Ranks banks and re-plans the remaining batches |
| `work/translate/play_order.json` | All 821 banks in estimated play order, with phase, zones and todo/tm/draft/reviewed counts |
| `work/translate/manifest_playorder.json` | Re-ordered plan for the remaining work, batches R001–R069 (manifest batch schema plus `phase` and `replaces_old_batches`) |

Regenerate with (run from `work/`):

```
python3 translate/scripts/build_bank_maps.py
python3 translate/scripts/build_playorder.py
```

Both are read-only on `banks/` and `manifest.json`, and each takes a few seconds.

## Method

1. **Map headers (arm9).** The hack's arm9 is uncompressed. It holds the pret `MapHeader` table (24 bytes × 540) at `0xF37C4`, found by a structural scan; the same scan finds the US table. Each zone gives:
   - `msgBank`: the a027 bank that the map's own scripts print from;
   - `scriptsBank` and `scriptHeaderBank` (a/0/1/2), `eventsBank` (a/0/3/2) and `matrixId`;
   - **`mapsec`**: the location name the player sees, which is the string id in a027/0272;
   - the region bit.

   Diffing against the US header table shows that 54 zones changed `mapsec`: the hack moved them.
2. **Common scripts.** `sScriptBankMapping` in arm9 at `0xF70E0` holds 30 × {scriptIdLo, scr file, msg bank}. These std scripts (TV, Pokémon Center, item balls, trainers, Pokéathlon, …) print from fixed banks on every map. Examples: 0038 (misc/trainer/init), 0722 (TV), 0044 (link reception) and 0657 (Pokédex evaluation).
3. **Connectivity.** Warps come from a/0/3/2; coord events are 16 bytes there, not 12. Outdoor adjacency comes from overworld matrix 0 (a/0/4/1, 47×17 header layer).
4. **Story order.** `STORY` in `build_playorder.py` lists the locations in playing order:
   - Kanto first: Pallet → Route 1 → Viridian → Route 22 → Route 2 → Viridian Forest → Pewter → Route 3 → Mt. Moon → Route 4 → Cerulean → Routes 24/25 → … → Cinnabar → Victory Road → Indigo Plateau/League → Routes 26–28 → Mt. Silver (Silver Conference);
   - then Johto from New Bark, in vanilla order.

   The Kanto part follows the scenes the translators logged for B032–B057. The Johto part is vanilla order and has not yet been checked against the hack's scripts. Story flags were not decoded.

   A zone takes the rank of its `mapsec`. Zones whose location is not on the route (the Sevii-like islands, Alto Mare, Resort Zone …) are side content. They attach, by BFS over warps and adjacency, to the nearest route zone. For example, Alto Mare Waters is entered from Rock Tunnel. A bank ranks at its earliest zone.
5. **Banks that no map header loads** are placed by hand in `EXPLICIT`, or by category otherwise:
   - move/item/ability/berry descriptions are "first hour";
   - trainer battle text (0718) and walking-Pokémon lines (0258) are a review pass, because they already have v3 English (`tm`);
   - HG Pokédex text (0791) goes before Johto;
   - phone, radio, TV shows, Frontier, Pokéathlon and minigames come after Johto;
   - link/Wi-Fi, debug, and the SS/Platinum Pokédex variants (0792/0798), which HG never shows, come last.

**Status meaning.** The build exports `tm,draft,reviewed`. So in the game, **`todo` strings show Chinese**, while `tm` strings show unreviewed v3 English.

**Limits.**
- A map header binds one bank per zone. The HGSS script engine has no command that prints from another bank, so map text comes only from the header bank or the std banks.
- 125 zones point at bank 0003 (battle messages) as a "no text" placeholder; those bindings are ignored.
- Six small map banks are loaded by no header: 0076, 0095, 0096, 0104, 0565, 0612. They are kept in the side-content tier.

## Early game (Pallet → Cerulean/Route 25): still untranslated

All 43 map banks bound to these locations were checked. Only two still have Chinese, and both are vanilla Johto interiors that the hack moved into Kanto:

| bank | where it really is (zone, vanilla map) | old batch | todo (Chinese on screen) | tm (v3 English) |
|---|---|---|---|---|
| **0552** | **Viridian City**: zone 159 `MAP_VIOLET_POKEMON_SCHOOL`, entered from Viridian (Cynthia at the school, Poké Ball lessons) | B063 "Violet" | **107** | 95 |
| **0146** | **Mt. Moon**: zone 524 `MAP_EMBEDDED_TOWER_GROUDON_ROOM`, reached from Route 4 / Mt. Moon (Maxie's Groudon ritual) | B096 "Sinjoh/Embedded Tower" | **11** | 42 |

Text on every map from the first hour on, with no map binding:

| bank | what | todo | tm |
|---|---|---|---|
| 0722 | TV programmes (std_tv, including the TV in the player's house) | **62** | 1 |
| 0721 | TV interviewer (std 10150) | **23** | 16 |
| 0044 | Pokémon Center link-club reception (std 9000) | **133** | 39 |
| 0657 | Oak's Pokédex evaluation (std 9950) | 0 | 58 |
| 0738 | move descriptions | **452** | 451 |
| 0218 | item descriptions | **279** | 512 |
| 0712 | ability descriptions | **210** | 118 |
| 0243 | berry descriptions | **64** | 0 |
| 0718 | trainer battle text (from the first trainers on) | 16 | 1,701 |
| 0258 | walking-Pokémon reactions | 3 | 756 |
| 0791 | HG Pokédex entries (the dex page when you register a catch) | **1,372** | 68 |

Leftovers in banks marked done are symbols only, not Chinese: 0217 has 368 `ー`/`？？？` placeholders, and 0003, 0005, 0178, 0272, 0295, 0416, 0717, 0719, 0737 and 0790 have 1–3 each (`！`, `ＨＰ／ＰＰ`, `㊚/㊛`, `ＩＤＮｏ．`, `☆`). The full-width ones will look odd in an English build.

### Later Kanto maps that the old plan scheduled for Johto

| bank | real location | vanilla map | old batch | todo | tm |
|---|---|---|---|---|---|
| 0142 | Rock Tunnel | `MAP_CLIFF_CAVE` | B090 | 126 | 21 |
| 0053 | Lavender Town | `MAP_SPROUT_TOWER_2F` | B064 | 221 | 9 |
| 0547 | Celadon City (via the Route 2 SE gatehouse zone, now Celadon) | `MAP_CHERRYGROVE_SOUTHEAST_HOUSE` | B060 | 111 | 0 |
| 0090 | Fuchsia City | `MAP_SLOWPOKE_WELL_B2F` | B067 | 211 | 5 |
| 0546 | Cinnabar Island | `MAP_CHERRYGROVE_GUIDE_GENT_HOUSE` | B060 | 69 | 1 |
| 0593/0594 | Cinnabar Island | `MAP_GOLDENROD_GLOBAL_TERMINAL_2F/3F` | B072/B073 | 110 / 11 | 9 / 7 |
| 0587/0588 | Indigo Plateau (zones 194/195, linked to Dream World, the League entrance and Victory Road) | `MAP_GOLDENROD_DEPARTMENT_STORE_4F/5F` | B071/B072 | 251 / 205 | 2 / 9 |
| 0608 | Indigo Plateau (off Victory Road) | `MAP_ECRUTEAK_SOUTHWEST_HOUSE` | B078 | 173 | 41 |
| 0065 | Pokémon League | `MAP_GOLDENROD_RADIO_TOWER_3F` | B073/B074 | 103 | 0 |
| 0129 | Tohjo Falls | `MAP_TOHJO_FALLS_HIDDEN_ROOM` | B090 | 9 | 19 |
| 0599 | Cerulean Cave | `MAP_OLIVINE_NORTH_HOUSE` | B081 | 136 | 1 |

**Islands / Alto Mare cluster.** It is entered from Rock Tunnel (zone 452 → Alto Mare Waters), so it belongs to Kanto mid-game. Its banks are:
- 0059 Island Cave, 0084 Island Forest, 0087 Five Island;
- 0379 Secret Forest, 0384 Alto Mare Library, 0393 Alto Mare Waters (also used by the Route 42 gate and Mt. Mortar 2F);
- 0554 Four Island, 0562 Seven Island, 0570 Shipyard Ruins, 0578 One Island;
- 0582 Islander's House, 0601 Sky Pillar Peak, 0624 Ritual Shrine, 0625 Six Island.

Together they hold 1,250 todo strings. The island banks the old plan filed under Pallet or Vermilion (0440, 0441, 0443, 0483, 0540) are already done.

## New batch order (`manifest_playorder.json`)

The plan covers the old B060–B142: 33,860 CJK strings and 660k CJK characters, in 69 batches R001–R069. Every batch is ≤600 strings and ≤15k CJK characters. Ranges of a bank that the old plan split are re-joined, and a bank is split again only when it cannot fit in one batch (0718, 0738, 0218, 0791, 0713/0714, 0754, 0258).

| batches | phase | contents | strings |
|---|---|---|---|
| R001 | first hour | 0552 Viridian school, 0146 Mt. Moon Groudon room, 0722/0721 TV, 0044 PC reception, 0657 dex evaluation | 582 |
| R002–R005 | first hour (menus) | move, item, ability and berry descriptions | 2,049 |
| R006–R007 | Kanto mid | Rock Tunnel, Lavender, Celadon, Fuchsia, Cinnabar (rewired Johto interiors) | 910 |
| R008–R010 | Kanto side | Sevii-style islands and Alto Mare | 1,315 |
| R011–R012 | Kanto league | Indigo Plateau, Pokémon League, Tohjo Falls, Cerulean Cave | 947 |
| R013–R017 | review | trainer battle text 0718, walking-Pokémon 0258 (already English, v3) | 2,466 |
| R018–R020 | Pokédex | HG Pokédex entries 0791 | 1,440 |
| R021–R041 | Johto story | Cherrygrove → Routes 30/31 → Violet → Sprout Tower → Ruins/Union Cave → Azalea → Ilex → Goldenrod → Radio Tower → National Park → Ecruteak → Olivine → Frontier → Cianwood → Mortar → Mahogany → Rocket HQ → Lake of Rage → Ice Path → Blackthorn → Routes 45–48 → Sinjoh | 10,823 |
| R042–R059 | side features | std side banks (Frontier records, Pokéathlon, bug contest, Safari, scratch cards, Chatot), TV shows, radio, phone, Frontier, Pokéathlon, minigames, easy chat, Frontier trainer text, unreferenced map banks | 8,377 |
| R060–R069 | unused / link | SS/Platinum Pokédex text, link/Wi-Fi, debug | 4,951 |

**Open points**
- Check the Johto order against the hack's scripts once R021 starts. New Bark is already done.
- Decide whether R060+ is worth doing at all.
- If playtesting goes past Cerulean before R005 is finished, bring R006/R007 forward.
