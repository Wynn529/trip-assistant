"""C 新增：少走路规则、中文金额省略写法、模型防护词表的离线测试。"""

import json
import os
import unittest
from unittest.mock import Mock, patch

from travel_agent import TravelAgent
from travel_agent.contracts import TripRequest
from travel_agent.llm import DeepSeekInterpreter, _chinese_number


def model_reply(updates):
    return {"choices": [{"message": {"content": json.dumps({"updates": updates, "generic_ideas": []}, ensure_ascii=False)}}]}


class LowWalkingTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.agent = TravelAgent(live_model=False, live_weather=False)

    def test_low_walking_keeps_one_main_stop_per_day(self):
        base = TripRequest(city="成都", budget=2500, rain_days=[2])
        before = self.agent.turn("继续", base)
        after = self.agent.turn("尽量少走路", base)
        self.assertTrue(all(len(day["activities"]) == 2 for day in before.itinerary))
        self.assertTrue(all(len(day["activities"]) == 1 for day in after.itinerary))
        self.assertLess(after.total_cost, before.total_cost + 1)
        self.assertTrue(any("少走路" in change for change in after.changes))
        self.assertTrue(all(a["indoor"] for a in after.itinerary[1]["activities"]))

    def test_low_walking_applies_to_every_covered_city(self):
        from travel_agent.data.catalog import supported_cities
        for city in supported_cities():
            with self.subTest(city=city):
                result = self.agent.turn("尽量少走路", TripRequest(city=city, days=7, elderly=1, budget=100000))
                self.assertTrue(all(len(day["activities"]) <= 1 for day in result.itinerary))


class ChineseNumberTests(unittest.TestCase):
    def test_omitted_trailing_unit(self):
        for text, value in (("两千五", 2500), ("一万二", 12000), ("三百五", 350), ("两千零五", 2005),
                            ("两千五百", 2500), ("一万两千", 12000), ("十五", 15)):
            with self.subTest(text=text):
                self.assertEqual(_chinese_number(text), value)


class ModelGuardVocabularyTests(unittest.TestCase):
    def setUp(self):
        patches = [patch.dict(os.environ, {"DEEPSEEK_API_KEY": "unit-test-placeholder"}),
                   patch("travel_agent.llm.load_local_env")]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def parse(self, text, updates, previous=None):
        return DeepSeekInterpreter(live=True, transport=Mock(return_value=model_reply(updates))).parse(text, previous)

    def test_family_words_count_as_mentions(self):
        result, _, _ = self.parse("国庆带爸妈去成都玩四天，别太累",
                                  {"days": 4, "elderly": 2, "pace": "舒缓", "start_date": "2026-10-01"})
        self.assertEqual((result.elderly, result.days, result.start_date), (2, 4, "2026-10-01"))
        result, _, _ = self.parse("我跟老婆再带个娃去北京", {"city": "北京", "adults": 2, "children": 1, "elderly": 0})
        self.assertEqual((result.adults, result.children, result.elderly), (2, 1, 0))

    def test_guard_still_blocks_unmentioned_fields(self):
        previous = TripRequest(city="杭州", days=5, elderly=2)
        result, _, status = self.parse("预算降到2000元", {"city": "成都", "days": 3, "elderly": 0}, previous)
        self.assertEqual((result.city, result.days, result.elderly, result.budget), ("杭州", 5, 2, 2000))
        self.assertIn("已忽略本轮未涉及字段", status)

    def test_explicit_elderly_is_not_overridden_by_model(self):
        previous = TripRequest(elderly=1, assumed_fields=[])
        result, _, _ = self.parse("两个大人", {"adults": 2, "elderly": 0}, previous)
        self.assertEqual(result.elderly, 1)


class KinshipTermTests(unittest.TestCase):
    def test_family_terms_without_model(self):
        from travel_agent.llm import fallback_extract
        for text, party in (("带着老爸老妈去上海玩", (1, 2, 0)), ("带爸妈去成都三天", (1, 2, 0)),
                            ("我和老婆带个娃去北京", (2, 0, 1)), ("带爷爷奶奶和外婆去广州", (1, 3, 0)),
                            ("不带爸妈，去上海", (1, 0, 0)), ("带一位老人去成都", (1, 1, 0))):
            with self.subTest(text=text):
                result = fallback_extract(text)
                self.assertEqual((result.adults, result.elderly, result.children), party)


if __name__ == "__main__":
    unittest.main()
