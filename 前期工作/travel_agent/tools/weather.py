"""Live weather lookup with explicit range and failure states."""

from __future__ import annotations

import json
from datetime import date, timedelta
from urllib.parse import urlencode
from urllib.request import urlopen

from travel_agent.contracts import TripRequest, WeatherContext


def _get_json(url: str) -> dict:
    with urlopen(url, timeout=6) as response:
        return json.load(response)


def fetch_weather(request: TripRequest, today: date | None = None) -> WeatherContext:
    if not request.start_date:
        return WeatherContext("no_date", "尚未提供出发日期；天气暂不查询。")
    now = today or date.today()
    start = date.fromisoformat(request.start_date)
    last = start + timedelta(days=request.days - 1)
    if start < now:
        return WeatherContext("past", "出发日期已过，无法提供未来天气预报。")
    if (last - now).days > 15:
        return WeatherContext("out_of_range", "出发日期超出逐日预报范围；请在临近出发时重新查询。")
    try:
        if request.city in {"成都", "成都市", "Chengdu"}:
            latitude, longitude = 30.67, 104.06
        else:
            geo_url = "https://geocoding-api.open-meteo.com/v1/search?" + urlencode(
                {"name": request.city, "count": 1, "language": "zh", "format": "json"}
            )
            matches = _get_json(geo_url).get("results", [])
            if not matches:
                return WeatherContext("city_not_found", "天气服务未识别该城市；请核对城市名称。")
            latitude, longitude = matches[0]["latitude"], matches[0]["longitude"]
        forecast_url = "https://api.open-meteo.com/v1/forecast?" + urlencode(
            {
                "latitude": latitude,
                "longitude": longitude,
                "daily": "weather_code,precipitation_probability_max,temperature_2m_max,temperature_2m_min",
                "timezone": "auto",
                "forecast_days": 16,
            }
        )
        daily = _get_json(forecast_url).get("daily", {})
        results = []
        for index, day in enumerate(daily.get("time", [])):
            if request.start_date <= day <= last.isoformat():
                results.append(
                    {
                        "date": day,
                        "rain_probability": daily["precipitation_probability_max"][index],
                        "weather_code": daily["weather_code"][index],
                        "max_c": daily["temperature_2m_max"][index],
                        "min_c": daily["temperature_2m_min"][index],
                    }
                )
        if len(results) != request.days:
            return WeatherContext("incomplete", "天气服务返回的日期不完整；行程暂不使用天气自动调整。")
        return WeatherContext("ok", "已读取 Open-Meteo 逐日天气预报。", results)
    except (OSError, KeyError, ValueError, TypeError) as exc:
        return WeatherContext("error", f"天气查询失败（{type(exc).__name__}）；仍可生成不依赖天气的行程。")
