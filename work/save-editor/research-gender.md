# Gender editing

Read-only disassembly of the existing local Chinese v4.0.3 reference ROM,
2026-10-10. No downloads or ROM changes.

The native gender getter at ARM9 0x0206DD4A reads species from logical A+0
and personality ID from the header, then calls 0x0206F37C. It replaces bits
1–2 of logical B+24 with the result and recalculates the checksum. Editing
only the cached gender bits therefore cannot persist when this getter runs.

0x0206F37C loads base-species personal data (not form-specific data).
0x0206F3A0 reads personal field 0x12 (gender ratio): 0 is male-only,
254 female-only, 255 genderless, otherwise PID low byte < ratio means female.
The personal archive's ratio byte is offset 16. The editor's existing bundled species metadata supplies this ratio; no
reference-data changes are needed on current main.

The editor selects a new PID preserving PID % 25, low-bit ability parity,
natural shininess and the existing shiny override. It keeps the stored ability,
OT, nickname, nature override, forms, IVs, EVs and every unrelated plaintext byte.
It updates the cached gender, reshuffles all four blocks for the new PID,
recomputes the boxed checksum/encryption and re-encrypts the complete party tail
with the new PID. Exact no-ops retain the original bytes. Impossible genders
are rejected; fixed-gender species have a disabled choice in the UI.

Changing PID can change other personality-based details, including Spinda spots
and Wurmple's evolution branch. The UI discloses this. No claim is made that
all identity-dependent behavior stays unchanged.

Regression coverage uses an independent encrypted-record oracle across all 32
shuffle selectors, boxed/party sizes, both gender directions, five mixed ratios,
natural/override shiny combinations, and PID/override natures. It checks every
unrelated logical byte and decrypted party-tail byte, source immutability,
invalid inputs, fixed genders, stale cached gender repair, and save export /
reopen with either active save generation. Native save/reset/reload in an emulator
has not been run for this change; persistence evidence is the native getter
analysis and the exported-save round trip.
