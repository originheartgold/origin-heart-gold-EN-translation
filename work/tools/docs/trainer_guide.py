"""Reviewed trainer-page organization, independent of ROM slot order.

Order follows guide chapters rather than promising a mandatory encounter schedule.
Class labels remain the game's labels; these groups describe the guide's navigation.
"""

STORY_CLASSES = [
    ('Rival battles', {23, 90, 110}),
    ('Gym Leaders', {66, 67, 70, 72, 73, 74, 75, 76, 98, 103, 104, 105, 106, 107, 108}),
    ('Elite Four', {87, 88, 89, 112}),
    ('Champions', {127, 128}),
    ('Team Rocket bosses, Executives and elites',
     {17, 39, 40, 44, 45, 51, 69, 83, 84, 86, 95, 96, 114, 116, 117, 118, 124}),
    ('Other named Trainers', {0, 1, 91, 92, 93, 94, 109, 111, 119, 120, 121, 125, 126, 97, 99, 100, 101, 102}),
]

# Giovanni's initial Viridian battle uses the Rocket Boss class. Blue's live
# Viridian rematch shares a Rival record with his League battle. #261's Gym
# reference belongs to an uncalled script; it is not an initial Gym challenge.
STORY_OVERRIDES = {662: 'Gym Leaders', 727: 'Gym Leaders'}


def story_group(tid, cls, name=''):
    if tid in STORY_OVERRIDES:
        return STORY_OVERRIDES[tid]
    if name.strip() == 'Misty' and cls in {93, 103}:
        return 'Gym Leaders'
    if cls == 0 and not name.strip():
        return None
    return next((title for title, classes in STORY_CLASSES if cls in classes), None)


# Kanto: guide 01–07; Volcano Badge precedes Sabrina's Marsh trial (guide 05).
# Johto: guide 08–12; Jasmine precedes Chuck (guide 10 then 11).
# Whitney's singles record is also reused for rematches, so render it once and
# keep all of its battle contexts. #325 is Janine disguised as Koga, not the
# Soul Badge battle (guide 04's Fuchsia Gym trial).
GYM_CHALLENGES = [
    {'title': 'Kanto Gym challenges', 'leaders': [
        {'title': 'Brock', 'location': 'Pewter Gym', 'ids': [253]},
        {'title': 'Misty', 'location': 'Cerulean Gym', 'ids': [254]},
        {'title': 'Lt. Surge', 'location': 'Vermilion Gym', 'ids': [255]},
        {'title': 'Erika', 'location': 'Celadon Gym', 'ids': [256]},
        {'title': 'Koga', 'location': 'Fuchsia Gym', 'ids': [257]},
        {'title': 'Blaine', 'location': 'Cinnabar Island Gym', 'ids': [259]},
        {'title': 'Sabrina', 'location': 'Saffron Gym', 'ids': [258]},
        {'title': 'Giovanni', 'location': 'Viridian Gym', 'ids': [662]},
    ]},
    {'title': 'Johto Gym challenges', 'leaders': [
        {'title': 'Falkner', 'location': 'Violet Gym', 'ids': [20]},
        {'title': 'Bugsy', 'location': 'Azalea Gym', 'ids': [21]},
        {'title': 'Whitney', 'location': 'Goldenrod Gym', 'ids': [30, 714],
         'note': 'The challenge can use a partner battle or a single battle. The singles team is also used for rematches.'},
        {'title': 'Morty', 'location': 'Ecruteak Gym', 'ids': [31]},
        {'title': 'Jasmine', 'location': 'Olivine Gym', 'ids': [33]},
        {'title': 'Chuck', 'location': 'Cianwood Gym', 'ids': [34]},
        {'title': 'Pryce', 'location': 'Mahogany Gym', 'ids': [32]},
        {'title': 'Clair', 'location': 'Blackthorn Gym', 'ids': [35]},
    ]},
]
GYM_CHALLENGE_IDS = frozenset(tid for section in GYM_CHALLENGES
                              for leader in section['leaders'] for tid in leader['ids'])
LEADER_ORDER = tuple(leader['title'] for section in GYM_CHALLENGES
                     for leader in section['leaders']) + ('Blue',)
