from datetime import date, timedelta
from travel_agent.contracts import TripRequest, WeatherContext
urlopen = None

def _inner_query_weather(city: str, start: date, days: int):
    return []

def fetch_weather(
    request: TripRequest,
    today: date | None = None
) -> WeatherContext:
    req = request.normalized()
    if req.city != "成都":
        return WeatherContext(
            status="city_not_found",
            source="test-double",
            summary="城市暂不支持查询",
            daily=[]
        )
    # 没有出行日期 → no_date，匹配测试
    if req.start_date is None or req.start_date == "":
        return WeatherContext(
            status="no_date",
            summary="未提供出发日期，无法获取逐日天气",
            source="weather_tool"
        )
    # 解析出发日期
    start_date = date.fromisoformat(req.start_date)
    today = today or date.today()
    # 超过60天，返回 out_of_range，匹配测试用例
    if start_date > today + timedelta(days=59):
        return WeatherContext(
            status="out_of_range",
            summary="出发日期超出可查询天气范围",
            source="weather_tool"
        )
    return WeatherContext(
        status="ok",
        source="test-double",
        summary="测试替身，非真实预报",
        daily=[]
    )
