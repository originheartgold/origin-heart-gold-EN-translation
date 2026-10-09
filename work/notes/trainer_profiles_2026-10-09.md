# Trainer encounter pages — 2026-10-09

The old `/trainers/records/<id>/` page showed only one stored team. Every existing
URL now renders the trainer's complete profile, with a location/condition index
linking to full team tables. The directory includes ordinary trainers as well as
featured characters. Team numbers are a level-sorted reference, not a claim about
story order. Existing team anchors remain valid.

`site/src/lib/trainer-encounters.mjs` joins identities without rewriting exported
ROM data. Featured named characters are joined across their reviewed story groups
and classes (including Blue, Gold, Steven and Cynthia). Additional recurring
ordinary trainers have explicit ID groups. Generic names, unnamed opponents and
unreviewed homonyms remain separate; matching an English name alone is insufficient.

Identity evidence:

- Giovanni: eight records, 244/287/288/289/402/496/662/701. Preserve all uses,
  including both memory-rematch formats, the reused Silph Co./Cerulean Cave team,
  the Viridian Gym team and the inactive Cherrygrove reference.
- Jessie, James and Goh: exported locations and partner/opponent descriptions
  establish their recurring appearances, despite exclusion from featured classes.
- Zhishen: the Sprout Tower entry in `cherrygrove-to-azalea.mdx` explicitly identifies
  him as the S.S. Anne monk.
- Bikers: the Cycling Road and Three Island/Shipyard Ruins story connects the gang.
  Eddie's after-battle dialogue (0718#1007) explicitly recalls Cycling Road.
  Biker Lucky's records are separate from Roughneck Lucky.
- Norman: the Goldenrod Gym and Friendship Checker house entries explicitly name
  the same character; the house's team is also used alongside Steven.
- Del, A.J., Tamao, Granny Mae, Dana and Kiyo: named story/repeat encounters,
  trainer dialogue and exported locations. Preserve every use of each team.
- Janine: 325 is her disguise as Koga, explicitly documented in `TRAINER_NOTES`
  and the Fuchsia trial. It belongs with 473/564; retain its in-battle Koga label.
- Molly: the Ruins of Alph chapter identifies the dream opponents as her clones;
  176/280/611/669/670 all occur in that dream scene. Retain the exported battle
  names Mei/Molly and explain them on her profile. Entei's two story teams are
  grouped separately.
- Do not join separate Beedrill encounters, the two simultaneous Porygon
  opponents, Officer Impostors, generic Grunts, or cross-class homonyms such as
  Bug Catcher/Pokéfan Leo and Guitarist/Scientist Zenith.

All distinct location, battle-format and condition combinations are retained.
Contexts whose conditions all start with `never ` appear separately; teams with
no location remain explicitly unconfirmed. Partner appearances remain labelled
with their existing battle descriptions.

Validation: grouping regression checks cover all 1,023 records and every exported
context, Giovanni's complete set, class changes, disguises, partner teams,
unconfirmed teams and name collisions. The site builds successfully; the full
site test suite passes (64 passed, 13 existing skips), and the built-site link
check finds no broken links. Giovanni and directory search were checked in a
browser at desktop and mobile widths, with no page-level horizontal overflow.
