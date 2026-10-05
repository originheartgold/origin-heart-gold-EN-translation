# WIP RC6 device/playthrough candidate — 2026-10-05

Final independent high-effort review: [text_speed_final_rc6_review.md](text_speed_final_rc6_review.md).
No new actionable implementation defect or blocker was found. The reviewer passed
63 focused tests and independently reproduced the native payload. The coordinator
passed the full 487-test tooling suite on the frozen source, with zero failures,
errors or skips.

The build includes primary-checkout translation increment `1c86d11`, merged as
`7e1f97e`, plus the reviewed text-speed feature and shared-harness fixes. Build
source commit: `0f03f04` on `codex/text-speed-research`. This is a local WIP RC6
for device testing, not a published release or tag.

- Patch: `work/release/v1.0.0-rc6-wip/Origin_HeartGold_v4.0.3_EN_v1.0.0-rc6-wip.xdelta`
- Base: clean Pokémon HeartGold (USA), CRC32 `C180A0E9`.
- Built ROM SHA256: `ef4ede8b586b47aeab491bb70b5c350c9816ac8125eedfc91557939e8af2ecc1`.
- ROM/build report: `work/build/text-speed/rc6-wip/` (ROM is local only).
- Fresh validation: `work/build/text-speed/rc6-final-validation/`.
- Patch checksums, instructions and machine-readable receipt accompany the patch
  in its ignored release directory.

Full build verification and xdelta reapplication passed. The standalone artifact
check passed, including native verification and payload reproduction. A binary
comparison with the previously exercised candidate confirmed ARM9, ARM7, overlay
tables and the Options overlay are byte-identical. The only changed filesystem
members are `a/0/2/7` and `battle/string/battle_string.narc`.

The exact RC6 candidate's fresh native Options input suite passed seven groups of
assertions and 490 heap checks, with no reported memory/probe failures. The fresh
three-mode trainer-dialogue result is recorded in `native-modes/report.json`;
its identity matches the hash above and all three modes passed. Each printed
54 dialogue glyphs with matching completed text pixels and 257 heap checks;
observed NORMAL/FAST/INSTANT frame spans were 54/34/2. Together with the Options
suite, 1,261 heap checks completed without reported memory/probe failures. Older broad corpus/fallback evidence in
[text_speed_harness.md](text_speed_harness.md) belongs to the preceding translation
candidate and is not presented as a run on this ROM.

Valid old battery saves need no conversion and default to NORMAL. Changes to text
speed persist when saving through the game. New-save → old-ROM downgrade support
is out of scope. The user's device/playthrough test supplies coverage not provided
by the emulator checks; extended play, hardware and broader natural callback and
battle paths remain the documented testing limits.
