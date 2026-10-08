# Linguistic data sources

The user approved dictionary and pronunciation downloads on 2026-10-07. The
catalogue tool itself has no network operations.

## CC-CEDICT

- Author: CC-CEDICT contributors; published by MDBG; continuation of CEDICT by
  Paul Andrew Denisowski (1997–1998).
- Source: <https://www.mdbg.net/chinese/dictionary?page=cc-cedict>
- Download: <https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz>
- Snapshot: **2026-10-07T03:26:22Z**, 125,215 entries, v1 UTF-8 export containing
  traditional and simplified forms.
- License: [Creative Commons Attribution-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-sa/4.0/).
- SHA-256: `00e6c188df0056c42c0448386d0b4f532aa805d9fdd87aef139f72b421ace2f4`.
- Local copy: `vendor/cedict_1_0_ts_utf-8_mdbg.txt.gz` (ignored).
- Transformations: parse entries into reading/sense tables, convert numbered tones
  to marked Pinyin, associate dictionary forms with source-text spans. Definitions
  and their ordering are preserved. Derived dictionary data retains CC BY-SA 4.0
  attribution and share-alike requirements; it is kept separately from game text
  and project translations. HTML reports include attribution.

## pypinyin

- Authors: mozillazg and contributors; package copyright credits mozillazg and
  闲耘 (hotoo).
- Version: **0.55.0**, installed without dependencies into `vendor/python/`.
- Source: <https://github.com/mozillazg/python-pinyin/tree/v0.55.0>
- Distribution: <https://pypi.org/project/pypinyin/0.55.0/>
- License: [MIT](https://github.com/mozillazg/python-pinyin/blob/v0.55.0/LICENSE.txt).
- The original license is retained at
  `vendor/python/pypinyin-0.55.0.dist-info/licenses/LICENSE.txt`.
- Usage: automatic phrase-based Mandarin suggestions and alternative character
  readings. No automatic output is marked as human-reviewed. Tone sandhi is disabled.
- The upstream package identifies its character data as `pinyin-data` and its
  phrase data as `phrase-pinyin-data`. This project uses the package's bundled data,
  without fetching additional dictionaries.

The dictionary snapshot hash, package version, and installed package RECORD hash
are recorded in `sources.lock.json`. Catalogue metadata also records dictionary
headers and pronunciation settings used by each build.

## Existing project sources

Game-specific names come from `work/glossary/*.json` and active term records in
`work/translate/decisions/decisions.jsonl`, retaining their existing provenance,
scope, and review status. These are project translations, not dictionary glosses.
Map context comes from `work/translate/bank_maps.json`; batch context comes from
`manifest_playorder.json`. Source-text and translation credits remain those of the
existing project; see `work/notes/credits_and_sources.md`.
