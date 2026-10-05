# Trainers page review — 2026-10-05

Reviewed the original `site/src/pages/trainers/index.astro`, `TrainerCard.astro`, all 1,023 exported trainer records, classification in `gen_docs.py`, and chapter descriptions of Gym progression. This is a presentation/classification review; independent ROM/script audits cover the underlying battle data.

## Confirmed presentation defects

- Numeric trainer-slot ordering placed Johto before Kanto, Surge before Brock, and split every character's teams across the page. Use reviewed Gym challenge order and character subsections for remaining encounters.
- Class 103 is Misty's `Cerulean Trnr` class. All her records were placed under Other named Trainers, including Gym team 254 and rematch 721. Preserve the in-game class label but group her as a Gym Leader.
- Class 0 omitted Red (eight records), Copycat 341, Gold 260, and Tan Hean 760. Include named class-0 records; unnamed 306 remains a generic entry.
- Class 23 omitted Silver's eight records. Classes 39/40/44/45/69 omitted 17 Rocket Elite records for Will, Karen, Cassidy, Butch and Joy. Include these in rival/Rocket sections.
- The original Champions section is class-based, containing only Steven 490 and Cynthia 491. Blue, Gold, Yellow and others also have champion-room battle contexts. Avoid wording suggesting this section contains every League finale opponent; character cards retain all contexts.
- Eight originally featured records had no location: 488, 492, 706–711. Fifteen records overall are unlocated: 86, 89, 260, 440, 488, 492, 609, 706–711, 760, 947. Do not call them unused merely because the scanner found no location. Explain that availability has not been established. The statement that every other trainer is on its location page is false for these records.
- There were only six section navigation entries for 190 featured cards. Character headings and dedicated initial Gym sections substantially improve navigation. Preserve one `trainer-N` anchor per page; Whitney 714 is used for both a first challenge and rematches.
- Partner battles are included among these records. Introductory text should explicitly say that a card may be an ally team, rather than only an opponent.

## Ordering evidence

- Kanto guide chapters 01–07: Brock, Misty, Surge, Erika, Koga, Blaine, Sabrina, Giovanni. Chapter 05's Sabrina trial requires the Volcano Badge, so conventional Sabrina-before-Blaine order is wrong here.
- Chapter 04 confirms Soul Badge battle 257. Record 325 is Janine disguised as Koga, a preliminary encounter, and must not be presented as the Soul Badge team.
- Johto chapters 08–12: Falkner, Bugsy, Whitney, Morty, Jasmine, Chuck, Pryce, Clair. Jasmine appears in chapter 10 and Chuck's cave/Gym chapter follows in 11. This is guide progression, not a claim that every battle is rigidly ordered.
- Parent/context audit supplies verified Giovanni 662 and live Blue rematch 727 classification. The apparent initial Blue Gym reference for 261 is in an uncalled script and is excluded from initial Gym challenges.

## Implemented support

`work/tools/docs/trainer_guide.py` centralizes classification and reviewed initial challenge metadata. `test_trainer_guide.py` provides three regression checks covering order, omitted named classes and unique classification. Tests pass. Generator/export/page integration is handled by the coordinator.
