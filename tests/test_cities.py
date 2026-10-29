"""C 新增：多城市数据与规划的离线测试。不联网、不需要密钥。"""

import os
import unittest
from unittest.mock import patch

from travel_agent import TravelAgent
from travel_agent.contracts import TripRequest, WeatherContext
from travel_agent.data.catalog import find_city, supported_cities, validate_city
from travel_agent.rules.planner import build_city_plan


class CityCatalogTests(unittest.TestCase):
    def test_expected_cities_are_covered_and_hangzhou_is_not(self):
        self.assertEqual(supported_cities()[0], "成都")
        self.assertTrue({"成都", "北京", "上海", "广州", "西安", "重庆"} <= set(supported_cities()))
        self.assertIsNone(find_city("杭州"))

    def test_aliases_resolve(self):
        for name, city in (("成都市", "成都"), ("Chengdu", "成都"), ("北京市", "北京"), ("Xi'an", "西安")):
            with self.subTest(name=name):
                self.assertEqual(find_city(name)["city"], city)

    def test_find_city_returns_a_copy(self):
        find_city("北京")["hotels"].clear()
        self.assertEqual(len(find_city("北京")["hotels"]), 2)

    def test_every_new_city_file_is_valid(self):
        for city in supported_cities():
            if city == "成都":
                continue  # 成都的日程与单价在 rules/planner.py 中，chengdu.json 未改动
            with self.subTest(city=city):
                self.assertEqual(validate_city(find_city(city)), [])

    def test_prices_are_labeled_as_estimates(self):
        for city in supported_cities():
            data = find_city(city)
            with self.subTest(city=city):
                self.assertIn("估算", data["data_status"])
                self.assertTrue(all(h["source_type"] == "demo_estimate" for h in data["hotels"]))


class CityPlanTests(unittest.TestCase):
    def setUp(self):
        patches = [
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}),
            patch("travel_agent.llm.load_local_env"),
            patch("travel_agent.tools.weather.urlopen", side_effect=AssertionError("network forbidden")),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.agent = TravelAgent(live_model=False, live_weather=False)

    def test_covered_cities_get_estimated_budget(self):
        for city in supported_cities():
            with self.subTest(city=city):
                result = self.agent.turn(f"去{city}三天，预算3000元")
                self.assertEqual(result.request.city, city)
                self.assertNotEqual(result.budget_status, "unverified")
                self.assertEqual(result.total_cost, sum(i["amount"] for i in result.budget_items))
                self.assertIn(f"{city}样例数据", result.coverage)

    def test_rainy_days_are_indoor_and_elderly_days_are_friendly(self):
        for city in supported_cities():
            for days in range(1, 8):
                with self.subTest(city=city, days=days):
                    request = TripRequest(city=city, days=days, elderly=1, rain_days=[d for d in (1, 2) if d <= days])
                    result = self.agent.turn("继续", request)
                    self.assertEqual(len(result.itinerary), days)
                    for day in result.itinerary:
                        for activity in day["activities"]:
                            self.assertTrue(activity["elderly_friendly"])
                            if day["rainy"]:
                                self.assertTrue(activity["indoor"])

    def test_new_city_does_not_use_chengdu_rules(self):
        with patch("travel_agent.service.build_chengdu_plan", side_effect=AssertionError("must not call Chengdu rules")):
            result = self.agent.turn("去北京三天，预算5000元")
        self.assertEqual(result.request.city, "北京")
        names = {a["name"] for d in result.itinerary for a in d["activities"]}
        self.assertTrue(names <= {a["name"] for a in find_city("北京")["activities"]})

    def test_live_rain_forecast_switches_new_city_to_indoor(self):
        data = find_city("西安")
        request = TripRequest(city="西安", days=1)
        daily = [{"date": "2026-11-01", "rain_probability": 90}]
        plan, *_ = build_city_plan(request, WeatherContext("ok", "mock", daily), data)
        self.assertTrue(plan[0]["rainy"])
        self.assertEqual(plan[0]["rain_source"], "实时预报")
        self.assertTrue(all(a["indoor"] for a in plan[0]["activities"]))

    def test_weather_uses_city_coordinates_without_geocoding(self):
        from datetime import date, timedelta
        from travel_agent.tools import weather
        start = date.today() + timedelta(days=1)
        days = [(start + timedelta(days=i)).isoformat() for i in range(16)]
        forecast = {"daily": {"time": days, "precipitation_probability_max": [0] * 16, "weather_code": [0] * 16,
                              "temperature_2m_max": [20] * 16, "temperature_2m_min": [10] * 16}}
        urls = []
        def fake_get_json(url):
            urls.append(url)
            return forecast
        with patch.object(weather, "_get_json", side_effect=fake_get_json):
            result = weather.fetch_weather(TripRequest(city="西安", start_date=start.isoformat(), days=2))
        self.assertEqual(result.status, "ok")
        self.assertEqual(len(urls), 1)
        self.assertNotIn("geocoding", urls[0])
        self.assertIn("latitude=34.34", urls[0])

class BudgetFitTests(unittest.TestCase):
    """超预算时先降档、换便宜景点；仍不够才提示最低估算。"""

    def setUp(self):
        patcher = patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.agent = TravelAgent(live_model=False, live_weather=False)

    def test_minimum_budget_is_reachable_and_reported(self):
        for city in supported_cities():
            with self.subTest(city=city):
                base = TripRequest(city=city, days=3, adults=2, elderly=0, assumed_fields=[])
                floor = self.agent.turn("继续", TripRequest(**{**base.to_dict(), "budget": 0}))
                self.assertTrue(any("最低估算" in w for w in floor.warnings))
                exact = self.agent.turn("继续", TripRequest(**{**base.to_dict(), "budget": floor.total_cost}))
                self.assertEqual(exact.total_cost, floor.total_cost)
                self.assertEqual(exact.budget_status, "estimated_within_budget")
                below = self.agent.turn("继续", TripRequest(**{**base.to_dict(), "budget": floor.total_cost - 1}))
                self.assertEqual(below.budget_status, "estimated_over_budget")

    def test_long_trip_downgrades_hotel_instead_of_overspending(self):
        result = self.agent.turn("继续", TripRequest(city="成都", days=7, adults=2, elderly=0, budget=5000, assumed_fields=[]))
        hotel = next(item for item in result.budget_items if item["category"] == "住宿")
        self.assertIn("经济型", hotel["detail"])
        self.assertLessEqual(result.total_cost, 5000)
        self.assertEqual(result.budget_status, "estimated_within_budget")

    def test_generous_budget_makes_no_swaps(self):
        for city in supported_cities():
            with self.subTest(city=city):
                result = self.agent.turn("继续", TripRequest(city=city, days=3, adults=2, elderly=0, budget=100000, assumed_fields=[]))
                self.assertFalse(any("预算约束" in change for change in result.changes))

    def test_no_activity_repeats_within_a_day(self):
        for city in supported_cities():
            for days in range(1, 8):
                for rain in ([], list(range(1, days + 1))):
                    with self.subTest(city=city, days=days, rain=rain):
                        result = self.agent.turn("继续", TripRequest(city=city, days=days, elderly=1, budget=0, rain_days=rain))
                        for day in result.itinerary:
                            ids = [a["id"] for a in day["activities"]]
                            self.assertEqual(len(ids), len(set(ids)))


class HeadCountTests(unittest.TestCase):
    def test_total_head_count_means_adults_only(self):
        from travel_agent.llm import fallback_extract
        for text, travelers in (("去西安，我自己一个人", 1), ("一人出行，去重庆", 1), ("去成都三天，两个人", 2), ("上海4天，3人", 3)):
            with self.subTest(text=text):
                result = fallback_extract(text)
                self.assertEqual((result.travelers, result.elderly, result.children), (travelers, 0, 0))

    def test_explicit_party_is_not_overridden(self):
        from travel_agent.llm import fallback_extract
        result = fallback_extract("一个人去北京，带一位老人")
        self.assertEqual(result.elderly, 1)
        self.assertEqual(fallback_extract("十一个人去成都").adults, 1)  # 超出上限，保留原值并提示


if __name__ == "__main__":
    unittest.main()
