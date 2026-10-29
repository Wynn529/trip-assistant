"""City sample-data catalog: look up a city's JSON in travel_agent/data by name or alias.

C 新增。每个已收录城市一个 json 文件，格式与 chengdu.json 相同，
另含 day_plans / rainy_options / costs / latitude / longitude。
chengdu.json 未改动，其日程与单价仍由 rules/planner.py 中的成都配置提供。
"""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from importlib.resources import files

# 兼容 service.py 原先认可的写法。
LEGACY_ALIASES = {"chengdu": "成都"}


def _key(name: str) -> str:
    name = (name or "").strip()
    if name.endswith("市") and len(name) > 2:
        name = name[:-1]
    return name.lower()


@lru_cache(maxsize=1)
def _catalog() -> dict[str, dict]:
    by_name: dict[str, dict] = {}
    for entry in sorted(files("travel_agent.data").iterdir(), key=lambda item: item.name):
        if not entry.name.endswith(".json"):
            continue
        data = json.loads(entry.read_text(encoding="utf-8"))
        city = data.get("city")
        if not isinstance(city, str) or not city:
            continue
        for alias in [city, *data.get("aliases", [])]:
            by_name[_key(alias)] = data
    for alias, city in LEGACY_ALIASES.items():
        if _key(city) in by_name:
            by_name.setdefault(alias, by_name[_key(city)])
    return by_name


def find_city(name: str) -> dict | None:
    """返回城市数据的副本；未收录时返回 None。"""
    data = _catalog().get(_key(name))
    return copy.deepcopy(data) if data else None


def supported_cities() -> list[str]:
    """已收录城市名，成都排在最前。"""
    names = list(dict.fromkeys(data["city"] for data in _catalog().values()))
    return sorted(names, key=lambda name: (name != "成都", name))


def validate_city(data: dict) -> list[str]:
    """检查城市数据是否能被 build_city_plan 安全使用；返回问题列表，空列表表示通过。"""
    problems: list[str] = []
    activities = {item.get("id"): item for item in data.get("activities", [])}
    if {item.get("id") for item in data.get("hotels", [])} != {"comfort", "economy"}:
        problems.append("hotels 需要且只需要 comfort 与 economy 两档")
    for item in data.get("hotels", []):
        if type(item.get("room_per_night")) is not int or item["room_per_night"] <= 0:
            problems.append(f"酒店 {item.get('id')} 的 room_per_night 需为正整数")
    for item in activities.values():
        if type(item.get("price_per_person")) is not int or item["price_per_person"] < 0:
            problems.append(f"景点 {item.get('id')} 的 price_per_person 需为非负整数")
        if not isinstance(item.get("indoor"), bool) or not isinstance(item.get("elderly_friendly"), bool):
            problems.append(f"景点 {item.get('id')} 需标明 indoor 与 elderly_friendly")
    day_plans = data.get("day_plans", [])
    if len(day_plans) < 7:
        problems.append("day_plans 需覆盖 7 天")
    for index, plan in enumerate(day_plans, start=1):
        for activity_id in plan:
            if activity_id not in activities:
                problems.append(f"第{index}天引用了不存在的景点 {activity_id}")
    rainy = data.get("rainy_options", [])
    if len(rainy) < 3:
        problems.append("rainy_options 至少需要 3 个室内备选")
    for activity_id in rainy:
        if activity_id not in activities or not activities[activity_id].get("indoor"):
            problems.append(f"雨天备选 {activity_id} 不存在或不是室内")
        elif not activities[activity_id].get("elderly_friendly"):
            problems.append(f"雨天备选 {activity_id} 不适合老人，不能作为替换项")
    costs = data.get("costs", {})
    for name in ("meal_per_person_day", "transport_per_day"):
        tiers = costs.get(name, {})
        if any(type(tiers.get(tier)) is not int for tier in ("comfort", "economy")):
            problems.append(f"costs.{name} 需包含 comfort 与 economy 两档整数")
    for name in ("flex", "comfort_min_budget"):
        if type(costs.get(name)) is not int:
            problems.append(f"costs.{name} 需为整数")
    for name in ("latitude", "longitude"):
        if not isinstance(data.get(name), (int, float)):
            problems.append(f"缺少 {name}")
    return problems
