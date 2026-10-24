"""Plan-and-execute flow: extract, look up, validate, revise, explain."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Callable

from travel_agent.contracts import AgentResponse, TripRequest, WeatherContext
from travel_agent.llm import DeepSeekInterpreter
from travel_agent.rules.planner import build_chengdu_plan
from travel_agent.tools.weather import fetch_weather


class TravelAgent:
    def __init__(
        self,
        live_model: bool = False,
        live_weather: bool = True,
        weather_provider: Callable[[TripRequest], WeatherContext] | None = None,
    ):
        self.interpreter = DeepSeekInterpreter(live=live_model)
        self.live_weather = live_weather
        self.weather_provider = weather_provider or fetch_weather

    def turn(self, user_text: str, previous: TripRequest | None = None) -> AgentResponse:
        trace: list[dict[str, str]] = []
        request, ideas, extraction_status = self.interpreter.parse(user_text, previous)
        trace.append({"step": "需求提取", "detail": extraction_status})
        trace.append({"step": "约束记忆", "detail": f"{request.city}，{request.days}天，{request.travelers}人，预算¥{request.budget}，老人{request.elderly}人"})

        if self.live_weather:
            weather = self.weather_provider(request)
        else:
            weather = WeatherContext("disabled", "演示设置已关闭实时天气；未生成天气预报。")
        trace.append({"step": "天气工具", "detail": f"{weather.status}：{weather.summary}"})

        warnings: list[str] = []
        changes: list[str] = []
        if request.city in {"成都", "成都市", "Chengdu"}:
            coverage = "成都样例数据：景点和费用均为演示估算"
            itinerary, budget_items, total, changes, warnings = build_chengdu_plan(request, weather)
            trace.append({"step": "数据查询", "detail": "加载成都景点、酒店、餐饮及市内交通样例"})
            trace.append({"step": "约束检查", "detail": f"估算总额¥{total}；预算¥{request.budget}；雨天替换{len([x for x in changes if '替换' in x])}项"})
            within_budget = total <= request.budget
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
        else:
            coverage = "非成都城市：景点、酒店和交通建议均未核实"
            itinerary = [
                {
                    "day": day,
                    "date": weather.daily[day - 1]["date"] if weather.status == "ok" else "",
                    "rainy": day in request.rain_days,
                    "rain_source": "演示模拟" if day in request.rain_days else "",
                    "activities": [
                        {"name": ideas[(day - 1) % len(ideas)] if ideas else "当地博物馆或文化场馆（地点待核实）", "indoor": True, "price_per_person": None},
                        {"name": "市中心休闲活动（地点待核实）", "indoor": False, "price_per_person": None},
                    ],
                    "note": "只提供方向性建议；开放时间、路线、价格和预约均待核实。",
                }
                for day in range(1, request.days + 1)
            ]
            budget_items = []
            total = 0
            within_budget = False
            warnings = ["目的地不在已核实样例库中，无法计算可靠预算或推荐具体预订。"]
            if weather.status != "ok":
                warnings.append(weather.summary)
            trace.append({"step": "数据覆盖", "detail": coverage})
            trace.append({"step": "预算检查", "detail": "缺少可靠报价，预算状态为未核实"})
            answer = f"可以为{request.city}提供初步行程方向；当地景点、报价和交通班次均需进一步核对。"

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
        )

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
