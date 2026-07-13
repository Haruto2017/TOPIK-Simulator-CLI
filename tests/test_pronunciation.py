import unittest

from topik_sim.pronunciation import RULES, build_pronunciation_items, guide


class PronunciationRuleTests(unittest.TestCase):
    def test_all_rules_have_worked_examples(self):
        self.assertEqual(len(RULES), 7)
        for rule in RULES:
            self.assertTrue(rule["examples"])
            for written, spoken, gloss in rule["examples"]:
                # a sound change means written and spoken differ, both Hangul.
                self.assertNotEqual(written.replace(" ", ""), spoken.replace(" ", ""),
                                    f"{rule['id']}: {written}")
                self.assertTrue(gloss)

    def test_guide_shape(self):
        data = guide()
        self.assertIn("intro", data)
        self.assertEqual({r["id"] for r in data["rules"]},
                         {"yeoneum", "gyeongeum", "bieum", "yueum", "gyeokeum", "gugae", "hiat"})

    def test_drill_items_ask_for_the_spoken_form(self):
        items = build_pronunciation_items(seed=0, count=8)
        self.assertEqual(len(items), 8)
        for item in items:
            self.assertEqual(item["kind"], "pronunciation")
            self.assertEqual(item["accept"], [item["answer"]])
            self.assertEqual(item["speech"], item["answer"])  # TTS reads the sound
            self.assertIn("→", item["meaning"])

    def test_drill_can_focus_one_rule_and_is_deterministic(self):
        first = build_pronunciation_items(seed=3, count=5, rule_id="gyeongeum")
        second = build_pronunciation_items(seed=3, count=5, rule_id="gyeongeum")
        self.assertEqual(first, second)
        tense = {"학꾜", "식땅", "숙쩨", "입꾸", "책쌍"}
        self.assertTrue({i["answer"] for i in first} <= tense)


if __name__ == "__main__":
    unittest.main()
