"""Agent 模式真实调用检查（需要 .env 中的 DEEPSEEK_API_KEY，会产生少量调用费用）。

用法（项目根目录）：
    .\\.venv\\Scripts\\python.exe -B agent_live_check.py
    .\\.venv\\Scripts\\python.exe -B agent_live_check.py --save   # 同时保存证据到 docs/evidence/

天气默认关闭；加 --weather 联网查询天气。输出不包含密钥。
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter

from travel_agent import TravelAgent

PROMPTS = (
    "国庆后带着老爸老妈去上海玩三天，别太累，预算3000左右",
    "第二天好像要下雨",
    "预算再降到2000",
)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--weather", action="store_true")
    args = parser.parse_args()
    agent = TravelAgent(live_model=True, live_weather=args.weather, agent_mode=True)
    previous, rounds, all_agent = None, [], True
    for text in PROMPTS:
        start = perf_counter()
        result = agent.turn(text, previous)
        elapsed = round(perf_counter() - start, 2)
        previous = result.request
        is_agent = "Agent 模式" in result.extraction_status
        all_agent &= is_agent
        print(f"\n你：{text}\n智能体（{elapsed}s）：{result.answer}")
        print(f"需求：{result.request.city} {result.request.days}天 预算¥{result.request.budget} "
              f"成人{result.request.adults} 老人{result.request.elderly} 儿童{result.request.children} 雨天{result.request.rain_days}")
        for step in result.trace:
            if step["step"].startswith(("Agent", "回复校验")):
                print(f"  - {step['step']}：{step['detail']}")
        rounds.append({"input": text, "elapsed_seconds": elapsed, "response": result.to_dict()})
    print("\n结论：", "三轮均为真实 Agent 调用" if all_agent else "存在回退，见上方 Agent 回退记录")
    if args.save:
        now = datetime.now(timezone(timedelta(hours=8)))
        out = Path(__file__).resolve().parent / "docs" / "evidence" / f"agent-live-{now:%Y%m%d-%H%M%S}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "generated_at": now.isoformat(), "python": platform.python_version(),
            "mode": "agent, live DeepSeek" + (", live weather" if args.weather else ", weather off"),
            "all_rounds_agent": all_agent, "rounds": rounds,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print("证据已保存：", out)
    return 0 if all_agent else 1


if __name__ == "__main__":
    raise SystemExit(main())
