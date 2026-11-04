"""C 新增：Agent 模式（模型自主调用工具）的离线测试。用脚本化的假模型，不联网、不需要真实密钥。"""

import json
import os
import unittest
from unittest.mock import patch

from travel_agent import TravelAgent
from travel_agent.contracts import TripRequest
from travel_agent.llm import DeepSeekInterpreter


def call(name, args=None, call_id=None):
    return {"id": call_id or f"call_{name}", "type": "function",
            "function": {"name": name, "arguments": json.dumps(args or {}, ensure_ascii=False)}}


def say(*calls, content=""):
    return {"choices": [{"message": {"role": "assistant", "content": content, "tool_calls": list(calls)}}]}


class ScriptedModel:
    """按顺序返回预设回复，并记录每次收到的请求。"""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.payloads = []

    def __call__(self, payload, key, base_url):
        self.payloads.append(json.loads(json.dumps(payload, ensure_ascii=False)))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class AgentLoopTests(unittest.TestCase):
    def setUp(self):
        patches = [patch.dict(os.environ, {"DEEPSEEK_API_KEY": "unit-test-placeholder"}),
                   patch("travel_agent.llm.load_local_env"),
                   patch("travel_agent.tools.weather.urlopen", side_effect=AssertionError("network forbidden"))]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def agent(self, model):
        return TravelAgent(live_weather=False, interpreter=DeepSeekInterpreter(live=True, transport=model), agent_mode=True)

    def test_model_drives_tools_and_reply(self):
        model = ScriptedModel(
            say(call("update_request", {"city": "上海", "elderly": 2, "adults": 1, "days": 3, "budget": 3000})),
            say(call("plan_trip")),
            say(call("finish", {"reply": "已为你和爸妈安排上海3天行程，在预算内。",
                                "follow_up_questions": ["打算哪天出发？"]})),
        )
        result = self.agent(model).turn("带老爸老妈去上海玩三天，预算3000")
        self.assertEqual((result.request.city, result.request.elderly, result.request.travelers), ("上海", 2, 3))
        self.assertNotEqual(result.budget_status, "unverified")
        self.assertTrue(result.answer.startswith("已为你和爸妈安排上海3天行程"))
        self.assertIn("打算哪天出发？", result.answer)
        self.assertIn("Agent 模式", result.extraction_status)
        steps = [t["detail"] for t in result.trace if t["step"].startswith("Agent 第")]
        self.assertEqual(len(steps), 3)
        self.assertTrue(steps[0].startswith("调用 update_request"))
        self.assertEqual(len(model.payloads), 3)
        self.assertEqual(model.payloads[0]["tools"][0]["function"]["name"], "update_request")
        tool_message = model.payloads[1]["messages"][-1]
        self.assertEqual(tool_message["role"], "tool")

    def test_agent_observes_over_budget_and_replans(self):
        model = ScriptedModel(
            say(call("update_request", {"city": "成都", "days": 7, "budget": 1000})),
            say(call("plan_trip")),
            say(call("update_request", {"days": 3})),
            say(call("plan_trip")),
            say(call("finish", {"reply": "预算不够7天，我改成了3天。"})),
        )
        result = self.agent(model).turn("去成都七天，预算1000")
        self.assertEqual(result.request.days, 3)
        self.assertEqual(len(result.itinerary), 3)
        plans = [t for t in result.trace if "plan_trip" in t["detail"]]
        self.assertEqual(len(plans), 2)

    def test_invented_numbers_are_rejected(self):
        model = ScriptedModel(
            say(call("update_request", {"city": "成都"})),
            say(call("plan_trip")),
            say(call("finish", {"reply": "门票只要9元，总共123456元。"})),
        )
        result = self.agent(model).turn("去成都")
        self.assertNotIn("123456", result.answer)
        self.assertTrue(any("工具结果之外的数字" in t["detail"] for t in result.trace))

    def test_invalid_update_is_reported_back_to_model(self):
        model = ScriptedModel(
            say(call("update_request", {"days": 9})),
            say(call("update_request", {"days": 5})),
            say(call("plan_trip")),
            say(call("finish", {"reply": "已改为5天。"})),
        )
        result = self.agent(model).turn("去成都九天")
        self.assertEqual(result.request.days, 5)
        error_message = json.loads(model.payloads[1]["messages"][-1]["content"])
        self.assertFalse(error_message["ok"])

    def test_system_plans_if_model_forgets(self):
        model = ScriptedModel(
            say(call("update_request", {"city": "北京"})),
            say(call("finish", {"reply": "好的。"})),
        )
        result = self.agent(model).turn("去北京")
        self.assertEqual(result.request.city, "北京")
        self.assertTrue(any(t["step"] == "Agent 补充" for t in result.trace))
        self.assertTrue(result.itinerary)

    def test_model_failure_falls_back_to_pipeline(self):
        model = ScriptedModel(TimeoutError("down"), TimeoutError("down"), TimeoutError("down"))
        result = self.agent(model).turn("去成都三天，预算3000元")
        self.assertEqual(result.request.city, "成都")
        self.assertEqual(result.trace[0]["step"], "Agent 回退")
        self.assertIn("TimeoutError", result.trace[0]["detail"])

    def test_unknown_tool_and_step_limit(self):
        model = ScriptedModel(*[say(call("fly_to_moon")) for _ in range(8)])
        result = self.agent(model).turn("去成都")
        self.assertTrue(any(t["step"] == "Agent 终止" for t in result.trace))
        self.assertTrue(result.itinerary)

    def test_previous_is_not_mutated(self):
        previous = TripRequest(city="杭州", budget=2500, rain_days=[2])
        before = previous.to_dict()
        model = ScriptedModel(say(call("update_request", {"budget": 2000})), say(call("plan_trip")),
                              say(call("finish", {"reply": "预算已调整。"})))
        result = self.agent(model).turn("预算降到2000", previous)
        self.assertEqual(previous.to_dict(), before)
        self.assertEqual((result.request.city, result.request.budget, result.request.rain_days), ("杭州", 2000, [2]))
        self.assertEqual(result.budget_status, "unverified")

    def test_no_key_uses_pipeline_without_calling_model(self):
        model = ScriptedModel()
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}):
            result = self.agent(model).turn("去成都三天")
        self.assertEqual(model.payloads, [])
        self.assertIn("未配置密钥", result.extraction_status)

    def test_agent_mode_off_by_default(self):
        self.assertFalse(TravelAgent(live_weather=False).agent_mode)


if __name__ == "__main__":
    unittest.main()
