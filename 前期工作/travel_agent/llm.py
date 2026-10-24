"""Low-cost DeepSeek extraction with a deterministic offline fallback."""

from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

from travel_agent.contracts import TripRequest


def load_local_env() -> None:
    path = Path(__file__).resolve().parent.parent / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _chinese_number(value: str) -> int:
    if value.isdigit():
        return int(value)
    digits = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    units = {"十": 10, "百": 100, "千": 1000, "万": 10000}
    total = current = 0
    for char in value:
        if char in digits:
            current = digits[char]
        elif char in units:
            unit = units[char]
            total += (current or 1) * unit
            current = 0
    return total + current


def fallback_extract(text: str, previous: TripRequest | None = None) -> TripRequest:
    result = TripRequest(**(previous.to_dict() if previous else {}))
    city_match = re.search(r"(?:去|到|目的地[是为]?)([\u4e00-\u9fff]{2,8}?)(?:旅游|游玩|玩|[一二三四五六七八九十0-9]+天|[，,。\s]|$)", text)
    if city_match:
        result.city = city_match.group(1).removesuffix("市")
    day_match = re.search(r"(?<![第0-9一二三四五六七])([0-9一二三四五六七]+)\s*天", text)
    if day_match:
        result.days = _chinese_number(day_match.group(1))
    budget_match = re.search(r"(?:预算|降到|改到|控制在)[^0-9一二三四五六七八九十百千万两]{0,4}([0-9]+|[一二三四五六七八九十百千万两]+)\s*(?:元|块)?", text)
    if budget_match:
        result.budget = _chinese_number(budget_match.group(1))
    date_match = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", text)
    if date_match:
        result.start_date = f"{int(date_match.group(1)):04d}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"
    if "不带老人" in text or "没有老人" in text:
        result.elderly = 0
    elif "老人" in text or "长辈" in text:
        result.elderly = max(1, result.elderly)
    if "小孩" in text or "孩子" in text:
        result.children = max(1, result.children)
    if "少走路" in text or "轻松" in text:
        result.pace = "舒缓"
        if "少走路" not in result.preferences:
            result.preferences.append("少走路")
    rain_day = re.search(r"第([0-9一二三四五六七]+)天.{0,8}(?:下雨|有雨)", text)
    if rain_day:
        day = _chinese_number(rain_day.group(1))
        result.rain_days = sorted(set(result.rain_days + [day]))
    if "天气转晴" in text or "不下雨" in text:
        result.rain_days = []
    return result.normalized()


class DeepSeekInterpreter:
    def __init__(self, live: bool = False):
        load_local_env()
        self.live = live
        self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
        self.base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")

    def parse(self, text: str, previous: TripRequest | None = None) -> tuple[TripRequest, list[str], str]:
        fallback = fallback_extract(text, previous)
        key = os.getenv("DEEPSEEK_API_KEY", "")
        if not self.live or not key:
            reason = "演示模式：使用本地需求提取" if not self.live else "未配置密钥：使用本地需求提取"
            return fallback, [], reason
        prompt = (
            "你是旅行需求提取器。只返回 JSON 对象，不写解释。根据当前消息和已有条件，"
            "给出完整字段：city,start_date,days,budget,adults,elderly,children,pace,rain_days,preferences,origin,"
            "generic_ideas（若非成都，最多3条不含具体价格与班次的通用建议）。"
            "保持用户未修改的已有条件；日期不明确时 start_date 为空字符串；不要猜测具体日期。"
            "rain_days 只记录用户明确提出的演示天气天数。数字用阿拉伯数字。"
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps({"today": date.today().isoformat(), "previous": previous.to_dict() if previous else {}, "message": text}, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 500,
            "temperature": 0,
        }
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                request = Request(
                    self.base_url + "/chat/completions",
                    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(request, timeout=20) as response:
                    raw = json.load(response)
                content = raw["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                allowed = {field: parsed[field] for field in TripRequest.__dataclass_fields__ if field in parsed}
                merged = fallback.to_dict()
                merged.update(allowed)
                result = TripRequest(**merged).normalized()
                ideas = parsed.get("generic_ideas", [])
                if not isinstance(ideas, list):
                    ideas = []
                note = "重试后成功" if attempt else "已提取需求"
                return result, [str(idea)[:100] for idea in ideas[:3]], f"DeepSeek {self.model} {note}"
            except (OSError, ValueError, KeyError, TypeError) as exc:
                last_error = exc
        return fallback, [], f"DeepSeek 两次调用失败（{type(last_error).__name__}），已回退本地提取"
