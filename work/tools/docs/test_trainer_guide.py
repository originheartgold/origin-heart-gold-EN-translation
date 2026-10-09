"""Regression checks for mistakes caused by using vanilla class/slot ordering."""
import unittest
from trainer_guide import GYM_CHALLENGES, GYM_CHALLENGE_IDS, STORY_CLASSES, story_group


class TrainerGuideTests(unittest.TestCase):
    def test_hack_gym_progression(self):
        kanto, johto = GYM_CHALLENGES
        self.assertEqual([x['title'] for x in kanto['leaders']],
                         ['Brock', 'Misty', 'Lt. Surge', 'Erika', 'Koga', 'Blaine', 'Sabrina', 'Giovanni'])
        self.assertEqual([x['title'] for x in johto['leaders']],
                         ['Falkner', 'Bugsy', 'Whitney', 'Morty', 'Jasmine', 'Chuck', 'Pryce', 'Clair'])
        ids = [tid for s in GYM_CHALLENGES for x in s['leaders'] for tid in x['ids']]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue({30, 714, 254, 662} <= GYM_CHALLENGE_IDS)
        self.assertTrue({325, 261, 727}.isdisjoint(GYM_CHALLENGE_IDS))

    def test_named_characters_do_not_disappear_due_to_class(self):
        for tid, cls, name, expected in [
            (254, 103, 'Misty', 'Gym Leaders'),
            (83, 93, 'Misty', 'Gym Leaders'),
            (727, 110, 'Blue', 'Gym Leaders'),
            (662, 17, 'Giovanni', 'Gym Leaders'),
            (29, 0, 'Red', 'Other named Trainers'),
            (341, 0, 'Copycat', 'Other named Trainers'),
            (171, 23, 'Silver', 'Rival battles'),
            (306, 0, '', None),
        ]:
            with self.subTest(tid=tid):
                self.assertEqual(story_group(tid, cls, name), expected)
        for cls in [39, 40, 44, 45, 69]:
            self.assertEqual(story_group(0, cls, 'named'), 'Team Rocket bosses, Executives and elites')

    def test_classes_have_one_group(self):
        classes = [cls for _, group in STORY_CLASSES for cls in group]
        self.assertEqual(len(classes), len(set(classes)))


if __name__ == '__main__':
    unittest.main()
