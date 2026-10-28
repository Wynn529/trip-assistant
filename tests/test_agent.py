"""Offline A acceptance tests. Runs with unittest or pytest; no API credentials needed."""

import json
from io import BytesIO
import os
import unittest
from datetime import date, timedelta
from unittest.mock import Mock, patch

from travel_agent import TravelAgent
from travel_agent.contracts import AgentResponse, TripRequest, WeatherContext
from travel_agent.llm import DeepSeekInterpreter, fallback_extract


def model_reply(updates=None, **extra):
    content = json.dumps({"updates": updates or {}, **extra}, ensure_ascii=False)
    return {"choices": [{"message": {"content": content}}]}


def weather_ok(request):
    start = date.fromisoformat(request.start_date or "2026-10-28")
    return WeatherContext("ok", "离线替身天气，非真实查询", [
        {"date": (start + timedelta(days=i)).isoformat(), "rain_probability": 80 if i == 1 else 0}
        for i in range(request.days)
    ], source="test-double")


class AgentTests(unittest.TestCase):
    def setUp(self):
        patches = [
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}),
            patch("travel_agent.llm.load_local_env"),
            patch("travel_agent.llm.urlopen", side_effect=AssertionError("network forbidden")),
            patch("travel_agent.tools.weather.urlopen", side_effect=AssertionError("network forbidden")),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.agent = TravelAgent(live_model=False, live_weather=False)

    def model(self, transport):
        os.environ["DEEPSEEK_API_KEY"] = "unit-test-placeholder"
        return DeepSeekInterpreter(live=True, transport=transport)

    def test_four_rounds_retain_state_and_budget(self):
        history = []
        previous = None
        for text in ("去成都三天，预算3000元，带一位老人", "第二天下雨，改成室内行程", "预算降到2500元", "尽量少走路"):
            response = self.agent.turn(text, previous)
            history.append(response)
            previous = response.request
            self.assertEqual(response.request.city, "成都")
            self.assertEqual(response.request.days, 3)
            self.assertEqual(response.request.elderly, 1)
            self.assertEqual(response.total_cost, sum(x["amount"] for x in response.budget_items))
            self.assertEqual(response.within_budget, response.total_cost <= response.request.budget)
        self.assertEqual([r.request.budget for r in history], [3000, 3000, 2500, 2500])
        self.assertEqual(history[0].request.rain_days, [])
        self.assertEqual(history[-1].request.rain_days, [2])
        self.assertTrue(all(x["indoor"] for x in history[1].itinerary[1]["activities"]))
        self.assertEqual(history[1].itinerary[1]["rain_source"], "演示模拟")
        self.assertIn("少走路", history[-1].request.preferences)
        self.assertNotIn("少走路", history[-2].request.preferences)
        self.assertTrue(any(t["step"] == "偏好交接" for t in history[-1].trace))
        self.assertFalse(any("B 基线规则尚未" in w for w in history[-1].warnings))
        self.assertEqual(history[2].request.budget, 2500)
        expected_status = "estimated_within_budget" if history[2].total_cost <= 2500 else "estimated_over_budget"
        self.assertEqual(history[2].budget_status, expected_status)

    @staticmethod
    def rule_fixture(request, weather):
        """Contract-compatible rule double; never evidence that B implemented it."""
        low_walking = "少走路" in request.preferences
        itinerary = [
            {
                "day": day, "date": "", "rainy": day in request.rain_days,
                "rain_source": "演示模拟" if day in request.rain_days else "",
                "activities": [
                    {"id": f"fixture-{day}-{i}", "name": f"测试替身活动{day}-{i}",
                     "indoor": True, "price_per_person": 0}
                    for i in range(1 if low_walking else 2)
                ],
                "note": "测试替身，非真实推荐",
            }
            for day in range(1, request.days + 1)
        ]
        items = [{"category": "测试费用", "amount": 1390, "detail": "规则替身，非真实报价"}]
        changes = ["测试替身：少走路规则已将每天主要活动由2项减为1项。"] if low_walking else []
        return itinerary, items, 1390, changes, []

    def test_low_walking_rule_results_are_preserved_without_stale_warning(self):
        with patch("travel_agent.service.build_chengdu_plan", side_effect=self.rule_fixture) as planner:
            before = self.agent.turn("去成都三天，预算2500元，带一位老人")
            previous_snapshot = before.request.to_dict()
            after = self.agent.turn("尽量少走路", before.request)
        self.assertEqual(before.request.to_dict(), previous_snapshot)
        self.assertIn("少走路", planner.call_args.args[0].preferences)
        self.assertEqual([len(d["activities"]) for d in before.itinerary], [2, 2, 2])
        self.assertEqual([len(d["activities"]) for d in after.itinerary], [1, 1, 1])
        self.assertEqual(after.changes, ["测试替身：少走路规则已将每天主要活动由2项减为1项。"])
        self.assertFalse(any("B 基线规则尚未" in w for w in after.warnings))
        self.assertFalse(any("待 B 接入" in t["detail"] for t in after.trace))

    def test_rule_unmet_constraint_warning_is_not_hidden(self):
        message = "测试替身：少走路约束未满足，室内备选不足，请人工核对。"
        def unmet_rule(request, weather):
            itinerary, items, total, _, _ = self.rule_fixture(request, weather)
            return itinerary, items, total, [], [message]
        with patch("travel_agent.service.build_chengdu_plan", side_effect=unmet_rule):
            result = self.agent.turn("去成都三天，尽量少走路")
        self.assertIn(message, result.warnings)
        self.assertEqual(result.changes, [])
        self.assertFalse(any("优化已成功" in x["detail"] for x in result.trace))

    def test_lower_budget_can_keep_an_already_affordable_plan(self):
        with patch("travel_agent.service.build_chengdu_plan", side_effect=self.rule_fixture) as planner:
            first = self.agent.turn("去成都三天，预算3000元")
            second = self.agent.turn("预算降到2500元", first.request)
        self.assertEqual(first.request.budget, 3000)
        self.assertEqual(second.request.budget, 2500)
        self.assertEqual(planner.call_count, 2)
        self.assertEqual(planner.call_args.args[0].budget, 2500)
        for result in (first, second):
            self.assertEqual(result.total_cost, 1390)
            self.assertEqual(result.total_cost, sum(x["amount"] for x in result.budget_items))
            self.assertTrue(result.within_budget)
            self.assertEqual(result.budget_status, "estimated_within_budget")

    def test_non_chengdu_preference_trace_does_not_claim_chengdu_rule_execution(self):
        with patch("travel_agent.service.build_chengdu_plan", side_effect=AssertionError("must not call Chengdu rules")) as planner:
            result = self.agent.turn("去杭州三天，尽量少走路")
        planner.assert_not_called()
        self.assertIn("少走路", result.request.preferences)
        self.assertEqual(result.budget_status, "unverified")
        detail = next(x["detail"] for x in result.trace if x["step"] == "偏好交接")
        self.assertIn("未执行成都规划规则", detail)
        self.assertNotIn("已传入规划规则", detail)

    def test_previous_is_not_mutated(self):
        previous = TripRequest(rain_days=[2], preferences=["文化"])
        before = previous.to_dict()
        current = self.agent.turn("尽量少走路，第三天下雨", previous)
        self.assertEqual(previous.to_dict(), before)
        self.assertEqual(current.request.rain_days, [2, 3])

    def test_defaults_are_explicitly_unconfirmed(self):
        result = self.agent.turn("帮我规划旅行")
        self.assertIn("city", result.request.assumed_fields)
        self.assertIn("elderly", result.request.assumed_fields)
        self.assertTrue(any("未经用户确认" in w for w in result.warnings))

    def test_explicit_fields_remove_assumptions(self):
        result = self.agent.turn("去杭州两天，预算0元，不带老人")
        self.assertFalse({"city", "days", "budget", "elderly"} & set(result.request.assumed_fields))
        self.assertEqual(result.request.elderly, 0)

    def test_no_key_never_calls_model(self):
        transport = Mock(side_effect=AssertionError("unexpected model call"))
        interpreter = DeepSeekInterpreter(live=True, transport=transport)
        agent = TravelAgent(live_weather=False, interpreter=interpreter)
        response = agent.turn("去成都三天")
        transport.assert_not_called()
        self.assertIn("未配置密钥", response.extraction_status)
        self.assertTrue(any("未配置密钥" in w for w in response.warnings))

    def test_model_timeout_retries_twice_and_preserves_state(self):
        transport = Mock(side_effect=TimeoutError("do not expose this raw body"))
        interpreter = self.model(transport)
        previous = TripRequest(city="杭州", rain_days=[2], preferences=["文化"])
        result, ideas, status = interpreter.parse("预算降到2500元", previous)
        self.assertEqual(transport.call_count, 2)
        self.assertEqual(result.city, "杭州")
        self.assertEqual(result.rain_days, [2])
        self.assertEqual(result.budget, 2500)
        self.assertEqual(ideas, [])
        self.assertIn("回退", status)
        self.assertNotIn("raw body", status)

    def test_bad_json_falls_back(self):
        transport = Mock(return_value={"choices": [{"message": {"content": "not json"}}]})
        response = TravelAgent(live_weather=False, interpreter=self.model(transport)).turn("去成都三天")
        self.assertIn("JSONDecodeError", response.extraction_status)
        self.assertEqual(transport.call_count, 2)
        self.assertEqual(len(response.itinerary), 3)

    def test_invalid_model_shapes_fall_back(self):
        for raw in ({}, {"choices": []}, {"choices": [{"message": {"content": "[]"}}]}, None):
            with self.subTest(raw=raw):
                transport = Mock(return_value=raw)
                result, _, status = self.model(transport).parse("预算2500元", TripRequest(city="杭州"))
                self.assertEqual(result.city, "杭州")
                self.assertEqual(result.budget, 2500)
                self.assertIn("回退", status)

    def test_invalid_model_fields_rejected(self):
        for updates in ({"days": "3"}, {"days": True}, {"days": 8}, {"budget": -1}, {"budget": None},
                        {"rain_days": "2"}, {"rain_days": [False]}, {"rain_days": [4]},
                        {"preferences": [3]}, {"city": None}, {"start_date": "2026-02-30"},
                        {"pace": "飞快"}, {"adults": 20}, {"assumed_fields": []}, {"total_cost": 0}):
            with self.subTest(updates=updates):
                transport = Mock(return_value=model_reply(updates))
                result, _, status = self.model(transport).parse("尽量少走路", TripRequest(city="杭州", budget=2500))
                self.assertEqual(result.city, "杭州")
                self.assertEqual(result.budget, 2500)
                self.assertEqual(result.days, 3)
                self.assertIn("回退", status)

    def test_model_partial_merge_retains_conditions(self):
        transport = Mock(return_value=model_reply({"preferences": ["文化", "少走路"]}))
        previous = TripRequest(city="杭州", budget=2500, rain_days=[2], start_date="2026-10-28")
        result, _, status = self.model(transport).parse("多看文化场馆", previous)
        self.assertEqual((result.city, result.budget, result.start_date, result.rain_days), ("杭州", 2500, "2026-10-28", [2]))
        self.assertEqual(result.preferences, ["文化", "少走路"])
        self.assertIn("已提取", status)
        payload = transport.call_args.args[0]
        self.assertEqual(json.loads(payload["messages"][1]["content"])["previous"], previous.to_dict())

    def test_explicit_local_value_has_precedence(self):
        transport = Mock(return_value=model_reply({"budget": 9999}))
        result, _, _ = self.model(transport).parse("预算降到2500元", TripRequest())
        self.assertEqual(result.budget, 2500)

    def test_model_retry_success(self):
        transport = Mock(side_effect=[TimeoutError(), model_reply({"origin": "北京"})])
        result, _, status = self.model(transport).parse("北京出发")
        self.assertEqual(result.origin, "北京")
        self.assertIn("重试后成功", status)
        self.assertEqual(transport.call_count, 2)

    def test_http_adapter_builds_json_request(self):
        interpreter = self.model(None)
        response_body = json.dumps(model_reply({"origin": "北京"})).encode("utf-8")
        with patch("travel_agent.llm.urlopen", return_value=BytesIO(response_body)) as opener:
            result, _, status = interpreter.parse("北京出发")
        self.assertEqual(result.origin, "北京")
        request = opener.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertTrue(request.full_url.endswith("/chat/completions"))
        payload = json.loads(request.data)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(opener.call_args.kwargs["timeout"], 20)
        self.assertIn("已提取需求", status)

    def test_invalid_generic_ideas_fall_back(self):
        interpreter = self.model(Mock(return_value=model_reply(generic_ideas="bad")))
        self.assertIn("回退", interpreter.parse("去杭州三天")[2])

    def test_weather_exception_does_not_interrupt(self):
        provider = Mock(side_effect=TimeoutError("private query string"))
        result = TravelAgent(weather_provider=provider).turn("去成都三天，第二天下雨")
        self.assertEqual(result.weather.status, "error")
        self.assertEqual(result.weather.daily, [])
        self.assertEqual(len(result.itinerary), 3)
        self.assertTrue(all(a["indoor"] for a in result.itinerary[1]["activities"]))
        self.assertNotIn("private query", str(result.to_dict()))

    def test_weather_mock_success_and_live_rain(self):
        result = TravelAgent(weather_provider=weather_ok).turn("去成都三天，2026-10-28出发")
        self.assertEqual(result.weather.status, "ok")
        self.assertEqual(result.itinerary[1]["date"], "2026-10-29")
        self.assertEqual(result.itinerary[1]["rain_source"], "实时预报")
        self.assertTrue(all(a["indoor"] for a in result.itinerary[1]["activities"]))

    def test_incomplete_weather_has_no_forecast(self):
        result = TravelAgent(weather_provider=lambda r: WeatherContext("ok", "mock", [])).turn("去成都三天")
        self.assertEqual(result.weather.status, "incomplete")
        self.assertEqual(result.weather.daily, [])
        self.assertTrue(all(not d["date"] for d in result.itinerary))

    def test_invalid_weather_payloads_degrade(self):
        for payload in (None, WeatherContext("unexpected", "mock"), WeatherContext("ok", "mock", [None] * 3),
                        WeatherContext("ok", "mock", [{"date": "2026-10-28", "rain_probability": 0}] * 3),
                        WeatherContext("ok", "mock", [{"date": "2026-10-28", "rain_probability": "80"}] * 3),
                        WeatherContext("ok", "mock", [{"date": "2026-10-28", "rain_probability": float("nan")}] * 3)):
            with self.subTest(payload=payload):
                result = TravelAgent(weather_provider=lambda r: payload).turn("去成都三天")
                self.assertEqual(result.weather.status, "error")
                self.assertEqual(result.weather.daily, [])

    def test_weather_wrong_dates_degrade(self):
        result = TravelAgent(weather_provider=weather_ok).turn("2026-10-29出发")
        self.assertEqual(result.weather.status, "ok")
        def wrong_dates(request):
            request.start_date = "2026-11-01"
            return weather_ok(request)
        result = TravelAgent(weather_provider=wrong_dates).turn("2026-10-29出发")
        self.assertEqual(result.weather.status, "error")
        self.assertEqual(result.request.start_date, "2026-10-29")

    def test_provider_cannot_mutate_history(self):
        def mutating_provider(request):
            request.budget = 1
            request.preferences.append("injected")
            return WeatherContext("error", "mock failure")
        result = TravelAgent(weather_provider=mutating_provider).turn("预算2500元")
        self.assertEqual(result.request.budget, 2500)
        self.assertNotIn("injected", result.request.preferences)

    def test_failed_weather_discards_stale_daily(self):
        result = TravelAgent(weather_provider=lambda r: WeatherContext("error", "mock", [{"date": "2026-10-28"}])).turn("去成都三天")
        self.assertEqual(result.weather.daily, [])

    def test_disabled_weather_does_not_call_provider(self):
        provider = Mock(side_effect=AssertionError())
        result = TravelAgent(live_weather=False, weather_provider=provider).turn("去成都三天")
        provider.assert_not_called()
        self.assertEqual(result.weather.status, "disabled")

    def test_no_date_and_out_of_range(self):
        agent = TravelAgent()
        self.assertEqual(agent.turn("去成都三天").weather.status, "no_date")
        distant = (date.today() + timedelta(days=60)).isoformat()
        result = agent.turn(f"去成都三天，{distant}出发")
        self.assertEqual(result.weather.status, "out_of_range")
        self.assertEqual(result.weather.daily, [])

    def test_non_chengdu_budget_unverified(self):
        result = self.agent.turn("去杭州三天，预算3000元")
        self.assertEqual(result.budget_status, "unverified")
        self.assertFalse(result.within_budget)
        self.assertEqual(result.budget_items, [])
        self.assertEqual(result.total_cost, 0)  # Compatibility sentinel, NOT a quote.
        self.assertTrue(all(a["price_per_person"] is None for d in result.itinerary for a in d["activities"]))
        self.assertIn("核对", result.answer)

    def test_non_chengdu_simulated_rain_uses_indoor_directions(self):
        result = self.agent.turn("去杭州三天，第二天下雨")
        self.assertTrue(result.itinerary[1]["rainy"])
        self.assertTrue(all(a["indoor"] for a in result.itinerary[1]["activities"]))

    def test_model_text_cannot_become_a_price_or_weather_fact(self):
        reply = model_reply(generic_ideas=["某景点门票1元，明天晴天"])
        result = TravelAgent(live_weather=False, interpreter=self.model(Mock(return_value=reply))).turn("去杭州三天")
        self.assertNotIn("门票1元", json.dumps(result.to_dict(), ensure_ascii=False))
        self.assertEqual(result.budget_status, "unverified")

    def test_seven_day_boundary(self):
        result = self.agent.turn("去成都七天，预算100000元")
        self.assertEqual(len(result.itinerary), 7)
        self.assertEqual(result.total_cost, sum(i["amount"] for i in result.budget_items))

    def test_zero_and_low_budget_are_not_raised_to_default(self):
        for budget in (0, 100):
            with self.subTest(budget=budget):
                result = self.agent.turn(f"去成都三天，预算{budget}元")
                self.assertEqual(result.request.budget, budget)
                self.assertEqual(result.budget_status, "estimated_over_budget")
                self.assertFalse(result.within_budget)
                self.assertIn("超预算", result.answer)

    def test_exact_budget_boundary(self):
        total = self.agent.turn("去成都三天，预算0元").total_cost
        result = self.agent.turn(f"去成都三天，预算{total}元")
        self.assertEqual(result.total_cost, result.request.budget)
        self.assertTrue(result.within_budget)
        self.assertEqual(result.budget_status, "estimated_within_budget")

    def test_mixed_or_decimal_local_numbers_do_not_crash_or_truncate(self):
        for text in ("预算3千元", "预算2500.5元", "去成都3十天", "第3十天下雨", "带3十位老人"):
            with self.subTest(text=text):
                result = self.agent.turn(text)
                self.assertEqual(result.request.budget, 3000)
                self.assertEqual(result.request.days, 3)
                self.assertIn("输入无效", result.extraction_status)

    def test_invalid_local_date_retains_last_reliable_date(self):
        previous = TripRequest(start_date="2026-10-28")
        result = self.agent.turn("出发日期改为2026-02-30", previous)
        self.assertEqual(result.request.start_date, "2026-10-28")
        self.assertTrue(any("输入无效" in w for w in result.warnings))

    def test_invalid_local_numbers_are_visible(self):
        for text in ("去成都八天", "预算-100元", "去成都-1天", "预算100001元"):
            with self.subTest(text=text):
                result = self.agent.turn(text)
                self.assertEqual(result.request.days, 3)
                self.assertEqual(result.request.budget, 3000)
                self.assertIn("输入无效", result.extraction_status)

    def test_counts_and_origin(self):
        result = fallback_extract("从北京出发，去成都三天，2名成人，2位老人，3个孩子")
        self.assertEqual((result.adults, result.elderly, result.children, result.origin), (2, 2, 3, "北京"))

    def test_chinese_budget_does_not_become_city(self):
        result = fallback_extract("预算降到两千五百元", TripRequest(city="杭州"))
        self.assertEqual(result.budget, 2500)
        self.assertEqual(result.city, "杭州")
        self.assertEqual(fallback_extract("预算一万两千元").budget, 12000)

    def test_cancel_specific_rain_day_and_shorten_trip(self):
        previous = TripRequest(rain_days=[2, 3])
        result = fallback_extract("第二天不下雨", previous)
        self.assertEqual(result.rain_days, [3])
        self.assertEqual(result.days, 3)
        self.assertEqual(fallback_extract("改成两天", previous).rain_days, [2])
        self.assertEqual(fallback_extract("天气转晴", previous).rain_days, [])

    def test_empty_input_keeps_previous(self):
        previous = TripRequest(city="杭州", budget=2500)
        result = self.agent.turn("  ", previous)
        self.assertEqual(result.request.to_dict(), previous.to_dict())
        self.assertTrue(any("输入为空" in w for w in result.warnings))

    def test_invalid_caller_contract_raises_clear_error(self):
        with self.assertRaises(TypeError):
            self.agent.turn(None)
        with self.assertRaises(ValueError):
            self.agent.turn("继续", TripRequest(days=8))

    def test_booking_dates(self):
        result = self.agent.turn("2026-11-05出发")
        self.assertEqual(result.booking_tasks[0]["due"], "2026-10-29")
        self.assertEqual(result.booking_tasks[-1]["due"], "2026-11-05")

    def test_json_and_legacy_constructor_compatibility(self):
        result = self.agent.turn("去成都三天")
        raw = json.loads(json.dumps(result.to_dict(), ensure_ascii=False))
        raw["request"] = TripRequest(**raw["request"])
        raw["weather"] = WeatherContext(**raw["weather"])
        self.assertEqual(AgentResponse(**raw).to_dict(), result.to_dict())
        for key in ("budget_status", "extraction_status", "schema_version"):
            raw.pop(key)
        self.assertEqual(AgentResponse(**raw).budget_status, "unverified")

    def test_inconsistent_rule_total_is_not_shown_as_verified(self):
        from travel_agent.rules.planner import build_chengdu_plan
        plan, items, total, changes, warnings = build_chengdu_plan(TripRequest(), WeatherContext("disabled", "mock"))
        for bad_items, bad_total in ((items, total + 1), (items, None), (items, "0"), (None, total), ([None], total), ([{"amount": -1}], -1)):
            with self.subTest(items=bad_items, total=bad_total):
                with patch("travel_agent.service.build_chengdu_plan", return_value=(plan, bad_items, bad_total, changes, list(warnings))):
                    result = self.agent.turn("去成都三天")
                self.assertEqual(result.budget_status, "unverified")
                self.assertEqual(result.budget_items, [])
                self.assertFalse(result.within_budget)
                self.assertNotIn("符合预算", result.answer)


if __name__ == "__main__":
    unittest.main()
