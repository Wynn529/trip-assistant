"""Plan-and-execute flow: extract, look up, validate, revise, explain."""

from __future__ import annotations

from datetime import date, timedelta
from math import isfinite
from typing import Callable

from travel_agent.contracts import AgentResponse, TripRequest, WeatherContext
from travel_agent.llm import DeepSeekInterpreter
from travel_agent.data.catalog import find_city
from travel_agent.rules.planner import build_chengdu_plan, build_city_plan
from travel_agent.tools.weather import fetch_weather


class TravelAgent:
    def __init__(
        self,
        live_model: bool = False,
        live_weather: bool = True,
        weather_provider: Callable[[TripRequest], WeatherContext] | None = None,
        interpreter: DeepSeekInterpreter | None = None,
    ):
        self.interpreter = interpreter or DeepSeekInterpreter(live=live_model)
        self.live_weather = live_weather
        self.weather_provider = weather_provider or fetch_weather

    def turn(self, user_text: str, previous: TripRequest | None = None) -> AgentResponse:
        trace: list[dict[str, str]] = []
        request, _ideas, extraction_status = self.interpreter.parse(user_text, previous)
        trace.append({"step": "需求提取", "detail": extraction_status})
        trace.append({"step": "约束记忆", "detail": f"{request.city}，{request.days}天，{request.travelers}人，预算¥{request.budget}，老人{request.elderly}人"})

        weather = self._weather(request)
        trace.append({"step": "天气工具", "detail": f"{weather.status}：{weather.summary}"})

        warnings: list[str] = []
        changes: list[str] = []
        # C 修改：按城市数据目录判断是否已收录；成都仍走 build_chengdu_plan。
        city_data = find_city(request.city)
        if city_data:
            city_name = city_data["city"]
            coverage = f"{city_name}样例数据：景点和费用均为演示估算"
            if city_name == "成都":
                itinerary, budget_items, total, changes, warnings = build_chengdu_plan(request, weather)
            else:
                itinerary, budget_items, total, changes, warnings = build_city_plan(request, weather, city_data)
            valid_cost = (
                type(total) is int and total >= 0
                and isinstance(budget_items, list) and bool(budget_items)
                and all(isinstance(item, dict) and type(item.get("amount")) is int and item["amount"] >= 0 for item in budget_items)
                and sum(item["amount"] for item in budget_items) == total
            )
            if not valid_cost:
                budget_items, total = [], 0
                warnings.append("规则费用数据无效或分项与总额不一致，已隐藏预算结论，请联系数据规则负责人核对。")
            trace.append({"step": "数据查询", "detail": f"加载{city_name}景点、酒店、餐饮及市内交通样例"})
            trace.append({"step": "约束检查", "detail": f"估算总额¥{total}；预算¥{request.budget}；雨天替换{len([x for x in changes if '替换' in x])}项"})
            within_budget = valid_cost and total <= request.budget
            budget_status = ("estimated_within_budget" if within_budget else "estimated_over_budget") if valid_cost else "unverified"
            if request.start_date == "":
                warnings.append("未提供准确出发日期；无法查询逐日天气，也无法计算提醒日期。")
            if weather.status not in {"ok", "no_date"}:
                warnings.append(weather.summary)
            if request.rain_days:
                warnings.append("雨天条件由用户指定，仅用于情境演示；不代表实时天气。")
            answer = (
                f"已为{request.travelers}人生成{request.city}{request.days}天行程；"
                f"估算¥{total}，预算¥{request.budget}。"
                + ("符合预算。" if within_budget else "当前仍超预算，请调整天数或预算。")
            )
            if not valid_cost:
                answer = f"已生成{request.city}行程方向，但预算校验失败；费用未核实。"
        else:
            coverage = "未收录城市：景点、酒店和交通建议均未核实"
            itinerary = [
                {
                    "day": day,
                    "date": weather.daily[day - 1]["date"] if weather.status == "ok" else "",
                    "rainy": day in request.rain_days or (
                        weather.status == "ok" and (weather.daily[day - 1].get("rain_probability") or 0) >= 55
                    ),
                    "rain_source": "演示模拟" if day in request.rain_days else (
                        "实时预报" if weather.status == "ok" and (weather.daily[day - 1].get("rain_probability") or 0) >= 55 else ""
                    ),
                    "activities": [
                        {"name": "当地博物馆或文化场馆（地点待核实）", "indoor": True, "price_per_person": None},
                        {"name": "室内休闲活动（地点待核实）", "indoor": True, "price_per_person": None},
                    ],
                    "note": "只提供方向性建议；开放时间、路线、价格和预约均待核实。",
                }
                for day in range(1, request.days + 1)
            ]
            budget_items = []
            total = 0
            within_budget = False
            budget_status = "unverified"
            warnings = ["目的地不在已核实样例库中，无法计算可靠预算或推荐具体预订。"]
            if weather.status != "ok":
                warnings.append(weather.summary)
            trace.append({"step": "数据覆盖", "detail": coverage})
            trace.append({"step": "预算检查", "detail": "缺少可靠报价，预算状态为未核实"})
            answer = f"可以为{request.city}提供初步行程方向；当地景点、报价和交通班次均需进一步核对。"

        if request.assumed_fields:
            labels = {"city": "城市", "days": "天数", "budget": "预算", "adults": "成人数", "elderly": "老人数", "children": "儿童数", "pace": "节奏"}
            names = "、".join(labels.get(name, name) for name in request.assumed_fields)
            warnings.append(f"以下字段仍使用演示默认值，未经用户确认：{names}；请确认同行人数和预算范围。")
        if "失败" in extraction_status or "未配置" in extraction_status or "输入无效" in extraction_status or "超出" in extraction_status:
            warnings.append(extraction_status)
        if not user_text.strip():
            warnings.append("本轮输入为空，保留已有条件；新对话使用明确标注的演示默认值。")
        if "少走路" in request.preferences:
            detail = (
                "少走路偏好已传入规划规则；实际调整与未满足约束见调整说明和警告。"
                if city_data
                else "已保留少走路偏好；当前仅提供未核实的行程方向，未执行成都规划规则或验证步行量。"
            )
            trace.append({"step": "偏好交接", "detail": detail})
        trace.append({"step": "预算状态", "detail": budget_status})
        warnings = list(dict.fromkeys(warnings))

        booking_tasks = self._booking_tasks(request)
        trace.append({"step": "结果生成", "detail": "输出行程、预算、提醒清单与调整原因"})
        return AgentResponse(
            request=request,
            weather=weather,
            itinerary=itinerary,
            budget_items=budget_items,
            total_cost=total,
            within_budget=within_budget,
            changes=changes,
            warnings=warnings,
            booking_tasks=booking_tasks,
            trace=trace,
            coverage=coverage,
            answer=answer,
            budget_status=budget_status,
            extraction_status=extraction_status,
        )

    def _weather(self, request: TripRequest) -> WeatherContext:
        if not self.live_weather:
            return WeatherContext("disabled", "演示设置已关闭实时天气；未生成天气预报。", source="none")
        try:
            # A provider must not mutate the canonical state carried to the next turn.
            weather = self.weather_provider(TripRequest(**request.to_dict()))
            if not isinstance(weather, WeatherContext):
                raise TypeError("weather provider must return WeatherContext")
            known = {"ok", "no_date", "past", "out_of_range", "city_not_found", "incomplete", "error", "disabled"}
            if weather.status not in known or not isinstance(weather.summary, str) or not isinstance(weather.source, str):
                raise ValueError("invalid weather status or summary")
            if weather.status != "ok":
                return WeatherContext(weather.status, weather.summary, source=weather.source)
            if not isinstance(weather.daily, list) or len(weather.daily) != request.days:
                return WeatherContext("incomplete", "天气日期不完整；未使用逐日天气，请稍后重新查询。", source=weather.source)
            dates = []
            for index, day in enumerate(weather.daily):
                if not isinstance(day, dict) or not isinstance(day.get("date"), str):
                    raise ValueError("invalid daily weather")
                current = date.fromisoformat(day["date"])
                if request.start_date and current != date.fromisoformat(request.start_date) + timedelta(days=index):
                    raise ValueError("weather date mismatch")
                probability = day.get("rain_probability")
                if probability is not None and (
                    type(probability) not in (int, float) or not isfinite(probability) or not 0 <= probability <= 100
                ):
                    raise ValueError("invalid rain probability")
                dates.append(current)
            if any(day != dates[0] + timedelta(days=index) for index, day in enumerate(dates)):
                raise ValueError("weather dates are not consecutive")
            return WeatherContext(weather.status, weather.summary, [dict(day) for day in weather.daily], weather.source)
        except Exception as exc:
            # Tool boundary: show only the exception type, never a URL, token or raw body.
            return WeatherContext("error", f"天气查询失败（{type(exc).__name__}）；未生成预报，请稍后查询，仍可使用用户指定的模拟雨天。", source="none")

    @staticmethod
    def _booking_tasks(request: TripRequest) -> list[dict[str, str]]:
        due = "待确定出发日期"
        departure = ""
        if request.start_date:
            start = date.fromisoformat(request.start_date)
            due = (start - timedelta(days=7)).isoformat()
            departure = start.isoformat()
        return [
            {"task": "核对并预订住宿", "due": due, "status": "待办"},
            {"task": "核对往返交通和证件", "due": due, "status": "待办"},
            {"task": "出发前复查天气，必要时带伞", "due": due, "status": "待办"},
            {"task": "检查身份证及票证", "due": departure or "出发前", "status": "待办"},
        ]