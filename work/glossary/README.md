# 起源心金 (Pokémon Origin HeartGold v4.0.3): zh-Hans → English glossary

This glossary covers the terms used in the hack author's spreadsheets in the project root. The spreadsheets are only read, never modified.

## Files

| file | contents |
|---|---|
| `species.json` | Species names, plus form variants from the encounter sheet (e.g. `六尾（形态1）` → Alolan Vulpix, `洛托姆1` → Heat Rotom) |
| `moves.json` | Moves from v3 技能, v4 招式变动, v4 新增技能机, the Sharpness/Mega Launcher lists, and the move-tutor list at the bottom of the items sheet |
| `abilities.json` | Official abilities plus about 30 custom hack abilities, which get proposed English names |
| `items.json` | Items from v4 3.2道具 and v3 道具. Rows the hack renamed, such as `暗黑球（改名黑暗球）`, map to the new name |
| `types.json` | All 19 official types, plus the 1-character abbreviations used in the sheets (飞, 普, 超, 地, 妖, 斗, 岩, 鬼) |
| `natures.json` | All 25 natures (none appear in the sheets, but they are included for completeness) |
| `locations.json` | Encounter maps, TM shop towns, Johto/Kanto towns and landmarks, and regions |
| `general.json` | UI and game terms: 精灵 = Pokémon, 属性 = Type, 梦特性 = Hidden Ability, 技能机 = TM, encounter methods, stats, and so on |
| `unmatched.md` | Every term that is custom, ambiguous or medium/low confidence, with a best guess and the reasoning |
| `manual_overrides.py` | Curated overrides: old 汉化 names, name collisions, custom content, form labels, general terms and abbreviations (`ABBREV`, `LOCAL_ABBREV`: short in-game spellings) |

The JSON files were generated once by `build_glossary.py` from the sheets and PokéAPI CSVs and have been edited by hand since (e.g. b70a7cc removed fuzzy keys), so they are now the source; the generator was removed on 2026-10-09 (git history keeps it). The method below records how the entries were first made.

Each entry has this format: `{"<中文>": {"en", "id", "source", "confidence", "note"?}}`. `id` is the PokéAPI id: species/move/ability/item/type/nature/location id. For items it is the PokéAPI item id, not the Gen 4 internal index. It is `null` for custom content.

## Method (first hit wins)

1. **manual**: the curated table in `manual_overrides.py`.
2. **pokeapi-zh-Hans**: an exact match on the official Simplified name (language 12), after normalising full-width characters.
3. **pokeapi-zh-Hant**: an exact match on the Traditional name (language 4), converted to Simplified with a character map. The map is learned from aligned zh-Hant/zh-Hans name pairs in PokéAPI, so no OpenCC is needed. This step catches older/Taiwanese names such as 火爆猴 (Primeape) and 负电拍拍 (Minun).
4. **fuzzy**, which has three parts:
   - **Sheet index.** The sheets carry official numbering: `0_NNN:` is the Gen 4 internal move, ability or item index, and 精灵数据 col A is the national dex number for #1–493. Most old 口袋群星-era names are resolved this way, e.g. 3D龙 → Porygon, 胡说树 → Sudowoodo, 拍打 → Pound, 剩饭 → Leftovers, 资料卡 → Data Card. Item indices go through `item_game_indices.csv` (generation 4). **Every index hit was reviewed by hand.** Slots the hack repurposed show up where the name and the index disagree. Some are handled by the name match (大声咆哮 = Snarl in the Sonic Boom slot, 月亮之力 = Moonblast, 魔法闪耀 = Dazzling Gleam, 疯狂伏特 = Wild Charge, 伏特替换 = Volt Switch). Others are fixed manually (嘻闹 = Play Rough, 绑紧 = Wring Out, 暴风 = Aeroblast?). For moves, the type is also checked against the official type.
   - **Rules.** `技能机NN` → TMNN, `秘传机NN` → HMNN, `N号道路/水路` → Route N (Kanto ≤28, Johto ≥29), and `X（改名Y）` → match Y.
   - **difflib.** Similarity against official names, used only as a last resort. It gives medium/low confidence, and in this build no entry relies on it.

**Name collisions to watch.** 绑紧 is official Bind but means Wring Out in this hack, where Bind is 捆绑. 暴风 is official Hurricane but sits in the Aeroblast slot with Aeroblast stats. 自行车 is the Gen 4 Bicycle. 黄金市 means Saffron (金黄市), not Goldenrod (满金市).

**English spelling.** The glossary uses the current official English names from PokéAPI, e.g. "Poké Ball", "Feint Attack", "Thunder Stone". The hack contains Gen 5–9 content, so a consistent modern baseline avoids mixing eras. Where a name exceeds the DS text box, the table below proposes the Gen 4 in-game compressed spelling (ThunderPunch, Parlyz Heal, Hi Jump Kick) or a new abbreviation in the same style.

**Locations.** PokéAPI has no zh-Hans names for Johto or Kanto, only Alola onward. Routes are resolved by rule. Towns and dungeons come from the manual table, which uses current official zh-Hans names plus the sheet's variants (彩虹市 = Celadon, 缘朱市/缘珠市 = Ecruteak, 绘皮镇 = Azalea). The free-text 获得方式 columns are not parsed for place names.

<!-- STATS -->

## Counts (auto-generated)

| category | terms | high-confidence | unresolved | sources |
|---|---|---|---|---|
| species | 897 | 894 (100%) | 0 | fuzzy 100, manual 19, pokeapi-zh-Hans 775, pokeapi-zh-Hant 3 |
| moves | 547 | 545 (100%) | 0 | fuzzy 148, manual 7, pokeapi-zh-Hans 392 |
| abilities | 284 | 254 (89%) | 0 | fuzzy 12, manual 38, pokeapi-zh-Hans 234 |
| items | 516 | 500 (97%) | 0 | fuzzy 383, manual 17, pokeapi-zh-Hans 116 |
| types | 27 | 27 (100%) | 0 | manual 8, pokeapi-zh-Hans 19 |
| natures | 25 | 25 (100%) | 0 | pokeapi-zh-Hans 25 |
| locations | 120 | 110 (92%) | 0 | fuzzy 47, manual 73 |

## Names over DS text limits (auto-generated)

Limits: species 10, moves 12, abilities 12, items 12 characters. Proposed abbreviations follow Gen 5+ in-game truncations where one exists.

| category | 中文 | official English | len | limit | proposed |
|---|---|---|---|---|---|
| species | 冰六尾 | Alolan Vulpix | 13 | 10 | Vulpix |
| species | 冰九尾 | Alolan Ninetales | 16 | 10 | Ninetales |
| species | 洛托姆3 | Frost Rotom | 11 | 10 | Rotom |
| species | 火箭雀 | Fletchinder | 11 | 10 | Fletchindr |
| species | 惩戒胡帕 | Hoopa Confined | 14 | 10 | Hoopa |
| species | 解放胡帕 | Hoopa Unbound | 13 | 10 | Hoopa |
| species | 好胜毛蟹 | Crabominable | 12 | 10 | Crabminabl (Gen 7 spelling) |
| species | 戽斗尖梭 | Barraskewda | 11 | 10 | Barrskewda |
| species | 焚焰蚣 | Centiskorch | 11 | 10 | Centskorch |
| species | 幽尾玄鱼♀ | Basculegion (F) | 15 | 10 | Bsculegion |
| species | 幽尾玄鱼♂ | Basculegion (M) | 15 | 10 | Bsculegion |
| species | 怖纳噬草 | Brambleghast | 12 | 10 | Bramblghst |
| species | 土龙节节 | Dudunsparce | 11 | 10 | Dudunsprce |
| species | 斯魔茶 | Poltchageist | 12 | 10 | Pltchgeist |
| species | 超级喷火龙X | Mega Charizard X | 16 | 10 | Charizard |
| species | 超级喷火龙Y | Mega Charizard Y | 16 | 10 | Charizard |
| species | 铠甲超梦 | Armored Mewtwo | 14 | 10 | ArmrMewtwo |
| species | 水晶大岩蛇 | Crystal Onix | 12 | 10 | CrystlOnix |
| species | 幽尾玄鱼 | Basculegion | 11 | 10 | Bsculegion |
| species | 蛇纹熊（形态1） | Galarian Zigzagoon | 18 | 10 | Zigzagoon |
| species | 隆隆石（形态1） | Alolan Graveler | 15 | 10 | Graveler |
| species | 狃拉（形态1） | Hisuian Sneasel | 15 | 10 | Sneasel |
| species | 千针鱼（形态1） | Hisuian Qwilfish | 16 | 10 | Qwilfish |
| species | 小拳石（形态1） | Alolan Geodude | 14 | 10 | Geodude |
| species | 火红不倒翁（形态1） | Galarian Darumaka | 17 | 10 | Darumaka |
| species | 穿山鼠（形态1） | Alolan Sandshrew | 16 | 10 | Sandshrew |
| moves | 龙息 | Dragon Breath | 13 | 12 | DragonBreath |
| moves | 草笛 | Grass Whistle | 13 | 12 | GrassWhistle |
| moves | 吸取之吻 | Draining Kiss | 13 | 12 | DrainingKiss |
| moves | 青草场地 | Grassy Terrain | 14 | 12 | GrassTerrain |
| moves | 薄雾场地 | Misty Terrain | 13 | 12 | MistyTerrain |
| moves | 魔法火焰 | Mystical Fire | 13 | 12 | MysticalFire |
| moves | 怪异电波 | Eerie Impulse | 13 | 12 | EerieImpulse |
| moves | 电气场地 | Electric Terrain | 16 | 12 | ElecTerrain |
| moves | 圆瞳 | Baby-Doll Eyes | 14 | 12 | BabyDollEyes |
| moves | 十万马力 | High Horsepower | 15 | 12 | HighHorsepwr |
| moves | 精神场地 | Psychic Terrain | 15 | 12 | PsychTerrain |
| moves | 精神之牙 | Psychic Fangs | 13 | 12 | PsychicFangs |
| moves | 广域战力 | Expanding Force | 15 | 12 | ExpandForce |
| moves | 双翼 | Dual Wingbeat | 13 | 12 | DualWingbeat |
| moves | 热沙大地 | Scorching Sands | 15 | 12 | ScorchSands |
| moves | 大地波动 | Terrain Pulse | 13 | 12 | TerrainPulse |
| moves | 秘剑千重涛 | Ceaseless Edge | 14 | 12 | CeaselesEdge |
| moves | 仆刀 | Kowtow Cleave | 13 | 12 | KowtowCleave |
| moves | 增强拳 | Power-Up Punch | 14 | 12 | PowerUpPunch |
| moves | 飞膝踢 | High Jump Kick | 14 | 12 | Hi Jump Kick |
| moves | 闪电拳 | Thunder Punch | 13 | 12 | ThunderPunch |
| moves | 原始力量 | Ancient Power | 13 | 12 | AncientPower |
| moves | 神速 | Extreme Speed | 13 | 12 | ExtremeSpeed |
| moves | 魔法闪耀 | Dazzling Gleam | 14 | 12 | DazzlngGleam |
| moves | 毒粉 | Poison Powder | 13 | 12 | PoisonPowder |
| moves | 电击 | Thunder Shock | 13 | 12 | ThunderShock |
| moves | 自爆 | Self-Destruct | 13 | 12 | Selfdestruct |
| moves | 爆裂拳 | Dynamic Punch | 13 | 12 | DynamicPunch |
| moves | 清醒 | Smelling Salts | 14 | 12 | SmellingSalt |
| moves | 羽毛舞 | Feather Dance | 13 | 12 | FeatherDance |
| abilities | 超级发射器 | Mega Launcher | 13 | 12 | MegaLauncher |
| abilities | 复眼 | Compound Eyes | 13 | 12 | Compoundeyes |
| abilities | 避雷针 | Lightning Rod | 13 | 12 | Lightningrod |
| abilities | 电气制造者 | Electric Surge | 14 | 12 | Elec. Surge |
| abilities | 精神制造者 | Psychic Surge | 13 | 12 | PsychicSurge |
| abilities | 搬岩 | Rocky Payload | 13 | 12 | RockyPayload |
| abilities | 化学变化气体 | Neutralizing Gas | 16 | 12 | Neutral. Gas |
| abilities | 亲子爱 | Parental Bond | 13 | 12 | ParentalBond |
| abilities | 钢之意志 | Steely Spirit | 13 | 12 | SteelySpirit |
| abilities | 始源之海 | Primordial Sea | 14 | 12 | PrimrdialSea |
| abilities | 终结之地 | Desolate Land | 13 | 12 | DesolateLand |
| abilities | 女王的威严 | Queenly Majesty | 15 | 12 | QueenlyMjsty |
| abilities | 一猩一意 | Gorilla Tactics | 15 | 12 | GorillaTctcs |
| abilities | 战斗切换 | Stance Change | 13 | 12 | StanceChange |
| abilities | 危险回避 | Emergency Exit | 14 | 12 | EmergncyExit |
| abilities | 遇水凝固 | Water Compaction | 16 | 12 | WaterCompact |
| abilities | 螺旋尾鳍 | Propeller Tail | 14 | 12 | PropellrTail |
| abilities | 热交换 | Thermal Exchange | 16 | 12 | ThermalExchg |
| items | 解麻药 | Paralyze Heal | 13 | 12 | Parlyz Heal |
| items | 力之粉 | Energy Powder | 13 | 12 | EnergyPowder |
| items | 雷之石 | Thunder Stone | 13 | 12 | Thunderstone |
| items | 小蘑菇 | Tiny Mushroom | 13 | 12 | TinyMushroom |
| items | 要石（已改名弱点保险） | Weakness Policy | 15 | 12 | Weak. Policy |
| items | 光粉 | Bright Powder | 13 | 12 | BrightPowder |
| items | 银粉 | Silver Powder | 13 | 12 | SilverPowder |
| items | 深海之牙 | Deep Sea Tooth | 14 | 12 | DeepSeaTooth |
| items | 深海之鳞 | Deep Sea Scale | 14 | 12 | DeepSeaScale |
| items | 黑眼镜 | Black Glasses | 13 | 12 | BlackGlasses |
| items | 不融冰 | Never-Melt Ice | 14 | 12 | NeverMeltIce |
| items | 弯勺 | Twisted Spoon | 13 | 12 | TwistedSpoon |
| items | 宝物袋（改为抗老喷雾） | Anti-Age Spray | 14 | 12 | AntiAgeSpray |
| items | 替身玩偶 | Substitute Doll | 15 | 12 | Sub. Doll |
| items | 大木博士的信（已改名警卫的信） | Guard's Letter | 14 | 12 | Guard Letter |
| items | 秘药 | Secret Potion | 13 | 12 | SecretPotion |
| items | 道具探测器 | Dowsing Machine | 15 | 12 | Dowsing MCHN |
| items | 杰尼龟喷壶 | Squirt Bottle | 13 | 12 | SquirtBottle |
| items | 黄柑果 | Yellow Apricorn | 15 | 12 | Ylw Apricorn |
| items | 蓝柑果 | Blue Apricorn | 13 | 12 | Blu Apricorn |
| items | 绿柑果 | Green Apricorn | 14 | 12 | Grn Apricorn |
| items | 桃柑果 | Pink Apricorn | 13 | 12 | Pnk Apricorn |
| items | 白柑果 | White Apricorn | 14 | 12 | Wht Apricorn |
| items | 黑柑果 | Black Apricorn | 14 | 12 | Blk Apricorn |
| items | 神秘石头 | Mystery Stone | 13 | 12 | MysteryStone |
