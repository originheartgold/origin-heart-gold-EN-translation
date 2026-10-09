# Save-editor feature comparison

Updated 2026-10-07. Both the standalone `sv` editor and guide use identical editor source, controls and tests.

| Requested feature | Current status |
|---|---|
| Gender | Compact male/female icons with sliding selected highlight beneath shiny; supported genders only; party and PC |
| Friendship, nickname/flag, experience | Editable; native growth curves recalculate party stats |
| Form selection | 383 native, encodable form mappings, including 16 Hisuian forms; species + form stored separately |
| Encounter and egg metadata | Ball, met level/location/date, egg location/date, origin game, language, encounter type and fateful flag |
| Pokémon OT | Name, gender, trainer ID and secret ID |
| Player profile | Name, gender and IDs editable; existing Pokémon OT data retained |
| Creation | Custom OT and encounter settings; defaults to player OT |
| Ribbons and markings | Removed from Pokémon UI at user request; core support retained |
| Fill box | Fill empty slots from selected Pokémon; distinct PIDs; existing occupants retained; one new shiny copy |
| Box tools | Species sort, fill, search and batch max IVs/friendship; move/copy/clone panel removed from Pokémon UI |
| Item reference | Price, held effect/parameter, Fling power/effect, field/battle/party-use metadata from local ROM; numeric effects |
| Individual Pokémon files | Removed from Pokémon UI at user request; core support retained |
| Showdown | Removed from Pokémon UI at user request; core support retained |
| Database/search | Search the loaded save’s party and all 24 PC boxes |
| Origin compatibility checks | Removed from Pokémon UI at user request; core support retained |
| Pokédex | Base species 1–1025 seen/caught flags; mark all; unrelated form/gender/language records retained |
| Mystery Gift | Removed from Trainer UI at user request; core support retained |

## Limits compared with PKHeX

- Compatibility checks are **not exhaustive legality analysis**. Origin’s custom mechanics, event distributions, evolution/transfer exceptions and encounter tables prevent applying vanilla PKHeX rules as an authoritative verdict.
- Encounter locations/game/language/type and item-effect metadata include numeric IDs. Complete Origin-specific friendly-name tables are not established.
- `.ohgpk4` and `.ohgwc4` are this editor’s native containers, not claims of vanilla `.pk4`/`.pgt`/`.pcd` compatibility. No cross-generation conversion or external event database is included.
- Showdown imports reject unsupported fields such as Tera Type and typed Hidden Power rather than silently discarding them. Set transfers carry battle settings, not complete encounter/OT/ribbon metadata.
- Mystery Gift imports validate only Pokémon/Egg/Item payloads. Special-card storage and other event types remain preserved; their injection is not validated.
- Pokédex form, gender and language records are preserved, not synthesized.
- Pokémon/item artwork still uses external image sources. Form artwork without a verified mapping shows the form’s name.
- Save formats and checksums have automated validation; loading the new controls’ output in the actual game remains unverified.

## Comparison sources

- Local Light Platinum `README.md` and `js/app.js` (read-only).
- [PKHeX](https://github.com/kwsch/PKHeX) and [its Pokémon editor](https://github.com/kwsch/PKHeX/blob/master/PKHeX.WinForms/Controls/PKM%20Editor/PKMEditor.cs).
- Local Origin rc5 ROM, existing guide species data and [native layout research](NATIVE_LAYOUT.md).
