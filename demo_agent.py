"""Run A's offline demonstration and optionally write reproducible evidence.

python -B demo_agent.py
python -B demo_agent.py --write-evidence
python -B demo_agent.py --interactive
python -B demo_agent.py --live  # Optional real-model check; weather remains off.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from travel_agent import TravelAgent
from travel_agent.contracts import TripRequest, WeatherContext
from travel_agent.llm import DeepSeekInterpreter

PROMPTS = (
    "去成都三天，预算3000元，带一位老人",
    "第二天下雨，改成室内行程",
    "预算降到2500元",
    "尽量少走路",
)


def record(agent, text, previous=None):
    start = perf_counter()
    response = agent.turn(text, previous)
    return {"input": text, "elapsed_seconds": round(perf_counter() - start, 6), "response": response.to_dict()}


def offline_evidence():
    agent = TravelAgent(live_model=False, live_weather=False)
    previous = None
    rounds = []
    for text in PROMPTS:
        entry = record(agent, text, previous)
        rounds.append(entry)
        previous = TripRequest(**entry["response"]["request"])
    def timeout_weather(request):
        raise TimeoutError("simulated weather timeout")
    failure_agent = TravelAgent(weather_provider=timeout_weather)
    scenarios = {
        "non_chengdu": record(agent, "去杭州三天，预算3000元"),
        "weather_failure": record(failure_agent, "去成都三天，第二天下雨"),
        "invalid_date": record(agent, "出发日期改为2026-02-30"),
        "zero_budget": record(agent, "去成都三天，预算0元"),
        "seven_days": record(agent, "去成都七天"),
    }
    with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}):
        scenarios["no_key"] = record(TravelAgent(live_model=True, live_weather=False), PROMPTS[0])
    def model_timeout(*args):
        raise TimeoutError("simulated model timeout")
    def bad_json(*args):
        return {"choices": [{"message": {"content": "invalid json"}}]}
    def valid_model(*args):
        return {"choices": [{"message": {"content": '{"updates": {"origin": "北京"}, "generic_ideas": []}'}}]}
    with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "offline-evidence-placeholder"}):
        for name, transport in (("model_timeout", model_timeout), ("bad_json", bad_json), ("mock_model_success", valid_model)):
            interpreter = DeepSeekInterpreter(live=True, transport=transport)
            scenarios[name] = record(TravelAgent(live_weather=False, interpreter=interpreter), "预算降到2500元", previous)
    def mock_weather(request):
        start = datetime.fromisoformat(request.start_date).date()
        return WeatherContext("ok", "离线天气替身，非真实联网预报", [
            {"date": (start + timedelta(days=i)).isoformat(), "rain_probability": 80 if i == 1 else 0}
            for i in range(request.days)
        ], source="test-double")
    scenarios["mock_weather_success"] = record(TravelAgent(weather_provider=mock_weather), "去成都三天，2026-10-28出发")
    scenarios["weather_out_of_range"] = record(TravelAgent(), f"去成都三天，{(datetime.now().date() + timedelta(days=60)).isoformat()}出发")
    return {
        "delivery_version": "A-1.2-review", "contract_schema_version": "1.0",
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "python": platform.python_version(),
        "mode": "offline; model/weather success cases are test doubles",
        "network_calls": 0,
        "rounds": rounds,
        "scenarios": scenarios,
    }


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-evidence", action="store_true")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.live and args.write_evidence:
        parser.error("真实手测使用独立终端记录；离线证据请移除 --live")
    if args.interactive:
        agent = TravelAgent(live_model=args.live, live_weather=False)
        previous = None
        print("A 智能体交互演示；天气关闭；输入 /reset 清空，/quit 退出。")
        while True:
            try:
                text = input("你：").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if text == "/quit":
                break
            if text == "/reset":
                previous = None
                print("已清空。")
                continue
            entry = record(agent, text, previous)
            previous = TripRequest(**entry["response"]["request"])
            print(json.dumps(entry, ensure_ascii=False, indent=2))
        return
    if args.live:
        agent = TravelAgent(live_model=True, live_weather=False)
        print(json.dumps(record(agent, PROMPTS[0]), ensure_ascii=False, indent=2))
        return
    evidence = offline_evidence()
    for index, entry in enumerate(evidence["rounds"], start=1):
        response = entry["response"]
        print(f"\n第{index}轮：{entry['input']}")
        print("需求：", json.dumps(response["request"], ensure_ascii=False))
        print("结果：", response["answer"])
        print("预算状态：", response["budget_status"])
        print("调整：", "；".join(response["changes"]) or "无")
        print("提示：", "；".join(response["warnings"]))
    print("\n离线场景：")
    for name, entry in evidence["scenarios"].items():
        response = entry["response"]
        print(f"{name}: weather={response['weather']['status']}; budget={response['budget_status']}; {response['extraction_status']}")
    if args.write_evidence:
        output = Path(__file__).resolve().parent / "docs" / "evidence" / "agent-demo.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        print("\n证据已保存：", output)


if __name__ == "__main__":
    main()
