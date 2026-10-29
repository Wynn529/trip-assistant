"""Live weather lookup with explicit range and failure states.

来源：真实查询逻辑来自文斓前期 `前期工作/travel_agent/tools/weather.py`；
no_date / out_of_range 等未联网状态的来源标签沿用 B 的版本。
Open-Meteo 逐日预报最多 16 天，超出即返回 out_of_range，不返回空的 ok。
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from urllib.parse import urlencode
from urllib.request import urlopen

from travel_agent.contracts import TripRequest, WeatherContext

FORECAST_DAYS = 16
CHENGDU_NAMES = {"成都", "成都市", "Chengdu"}
NOT_QUERIED = "weather_tool"


def _get_json(url: str) -> dict:
    with urlopen(url, timeout=6) as response:
        return json.load(response)


def fetch_weather(request: TripRequest, today: date | None = None) -> WeatherContext:
    if not request.start_date:
        return WeatherContext("no_date", "尚未提供出发日期；天气暂不查询。", source=NOT_QUERIED)
    now = today or date.today()
    start = date.fromisoformat(request.start_date)
    last = start + timedelta(days=request.days - 1)
    if start < now:
        return WeatherContext("past", "出发日期已过，无法提供未来天气预报。", source=NOT_QUERIED)
    if (last - now).days > FORECAST_DAYS - 1:
        return WeatherContext("out_of_range", "出发日期超出逐日预报范围（16 天内）；请在临近出发时重新查询。", source=NOT_QUERIED)
    try:
        if request.city in CHENGDU_NAMES:
            latitude, longitude = 30.67, 104.06
        else:
            geo_url = "https://geocoding-api.open-meteo.com/v1/search?" + urlencode(
                {"name": request.city, "count": 1, "language": "zh", "format": "json"}
            )
            matches = _get_json(geo_url).get("results", [])
            if not matches:
                return WeatherContext("city_not_found", "天气服务未识别该城市；请核对城市名称。", source="Open-Meteo")
            latitude, longitude = matches[0]["latitude"], matches[0]["longitude"]
        forecast_url = "https://api.open-meteo.com/v1/forecast?" + urlencode(
            {
                "latitude": latitude,
                "longitude": longitude,
                "daily": "weather_code,precipitation_probability_max,temperature_2m_max,temperature_2m_min",
                "timezone": "auto",
                "forecast_days": FORECAST_DAYS,
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
            return WeatherContext("incomplete", "天气服务返回的日期不完整；行程暂不使用天气自动调整。", source="Open-Meteo")
        return WeatherContext("ok", "已读取 Open-Meteo 逐日天气预报。", results, source="Open-Meteo")
    except (OSError, KeyError, ValueError, TypeError) as exc:
        return WeatherContext("error", f"天气查询失败（{type(exc).__name__}）；仍可生成不依赖天气的行程。", source="none")