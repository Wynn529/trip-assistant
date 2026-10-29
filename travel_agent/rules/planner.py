"""Curated city itineraries, weather substitution, and cost checks.

C 修改：把原先写死在 build_chengdu_plan 里的日程与费用单价抽成配置，
新增 build_city_plan 供其他已收录城市使用。成都的日程、单价与原版完全一致。
"""

from __future__ import annotations

import json
from importlib.resources import files

from travel_agent.contracts import TripRequest, WeatherContext


def load_chengdu_data() -> dict:
    path = files("travel_agent.data").joinpath("chengdu.json")
    return json.loads(path.read_text(encoding="utf-8"))


# 原 build_chengdu_plan 中的成都日程，原样保留。
CHENGDU_LAYOUT = {
    "day_plans": [
        ["wuhou", "jinli"],
        ["dufu", "kuanzhai"],
        ["science", "peoplespark"],
        ["jinsha", "sichuanmuseum"],
        ["wuhou", "peoplespark"],
        ["dufu", "science"],
        ["sichuanmuseum", "jinli"],
    ],
    "rainy_options": ["jinsha", "sichuanmuseum", "science"],
}

# 原 build_chengdu_plan 中的费用单价；城市数据文件的 costs 可逐项覆盖。
DEFAULT_COSTS = {
    "meal_per_person_day": {"comfort": 120, "economy": 100},
    "transport_per_day": {"comfort": 150, "economy": 110},
    "flex": 180,
    "comfort_min_budget": 2800,
    "comfort_max_travelers": 2,
}


def build_chengdu_plan(
    request: TripRequest, weather: WeatherContext
) -> tuple[list[dict], list[dict], int, list[str], list[str]]:
    data = load_chengdu_data()
    return build_city_plan(request, weather, {**CHENGDU_LAYOUT, **data})


def build_city_plan(
    request: TripRequest, weather: WeatherContext, data: dict
) -> tuple[list[dict], list[dict], int, list[str], list[str]]:
    activities = {item["id"]: item for item in data["activities"]}
    normal_days = data["day_plans"]
    rainy_options = data["rainy_options"]
    costs = {**DEFAULT_COSTS, **data.get("costs", {})}
    used: set[str] = set()
    itinerary: list[dict] = []
    changes: list[str] = []
    warnings = list(data["notes"])
    for day_number in range(1, request.days + 1):
        base = normal_days[day_number - 1]
        live_rain = (
            weather.status == "ok"
            and day_number <= len(weather.daily)
            and (weather.daily[day_number - 1].get("rain_probability") or 0) >= 55
        )
        rainy = day_number in request.rain_days or live_rain
        selected = []
        for activity_id in base:
            activity = activities[activity_id]
            replace = (rainy and not activity["indoor"]) or (
                request.elderly > 0 and not activity["elderly_friendly"]
            )
            if replace:
                replacement = next((x for x in rainy_options if x not in used and x not in selected), None)
                if replacement:
                    selected.append(replacement)
                    changes.append(f"第{day_number}天：将{activity['name']}替换为{activities[replacement]['name']}（雨天/行动强度约束）。")
                else:
                    warnings.append(f"第{day_number}天室内备选不足，请人工核对。")
            else:
                selected.append(activity_id)
        used.update(selected)
        day_activities = [activities[item_id].copy() for item_id in selected]
        itinerary.append(
            {
                "day": day_number,
                "date": weather.daily[day_number - 1]["date"] if weather.status == "ok" else "",
                "rainy": rainy,
                "rain_source": "演示模拟" if day_number in request.rain_days else ("实时预报" if live_rain else ""),
                "activities": day_activities,
                "note": "每天安排不超过两个主要地点，保留午间休息。" if request.elderly else "预留交通与用餐时间。",
            }
        )
    travelers = request.travelers
    hotels = {item["id"]: item for item in data["hotels"]}
    comfortable = request.budget >= costs["comfort_min_budget"] and travelers <= costs["comfort_max_travelers"]
    tier = "comfort" if comfortable else "economy"
    hotel = hotels[tier]
    if tier == "economy":
        changes.append("预算约束：住宿改为经济型酒店方案，并降低餐饮与市内交通估算。")
    nights = max(0, request.days - 1)
    tickets = sum(item["price_per_person"] * travelers for day in itinerary for item in day["activities"])
    meals = costs["meal_per_person_day"][tier] * travelers * request.days
    local_transport = costs["transport_per_day"][tier] * request.days
    items = [
        {"category": "住宿", "amount": hotel["room_per_night"] * nights, "detail": f"{hotel['name']} × {nights}晚（估算）"},
        {"category": "餐饮", "amount": meals, "detail": f"{travelers}人 × {request.days}天（估算）"},
        {"category": "市内交通", "amount": local_transport, "detail": "打车/公共交通组合（估算）"},
        {"category": "景点门票", "amount": tickets, "detail": "按样例单价估算，实际价格需核对"},
        {"category": "机动费用", "amount": costs["flex"], "detail": "临时支出预留"},
    ]
    total = sum(item["amount"] for item in items)
    if total > request.budget:
        warnings.append(f"估算费用 ¥{total} 超过预算 ¥{request.budget}；请提高预算、缩短行程或进一步减少项目。")
    if request.origin:
        warnings.append(f"出发地为{request.origin}；目前未接入城际交通报价，往返大交通仍未计入预算。")
    return itinerary, items, total, changes, warnings
