def get_weather(city: str, date, mock: bool = True):
    """
    mock=True 本地模拟，不联网；mock=False调用真实接口
    rain_source: user_simulate 用户模拟下雨 / api_forecast 接口预报
    """
    if city != "成都":
        return {
            "status":"error/city_not_found",
            "rain_source": None,
            "daily": [],
            "summary":"无法查询该城市天气"
        }

    if mock:
        # 用户模拟场景：第2天下雨，用于测试
        return {
            "status":"ok",
            "rain_source":"user_simulate",
            "daily": [{"day":1,"rain":False},{"day":2,"rain":True}],
            "summary":"模拟：第2天会下雨"
        }

    # 真实接口ok返回
    return {
        "status":"ok",
        "rain_source":"api_forecast",
        "daily": [{"day":1,"rain":False}],
        "summary":"天气晴朗"
    }


def weather_out_of_range_sample():
    """日期超出可查询范围样例"""
    return {
        "status":"out_of_range",
        "rain_source":None,
        "daily":[],
        "summary":"查询日期超出支持范围"
    }


if __name__ == "__main__":
    # 本地直接运行这个文件，可以打印看返回结果，给A的样例
    print("【ok模拟下雨】")
    print(get_weather("成都", None, mock=True))
    print("\n【城市不存在】")
    print(get_weather("北京", None, mock=True))
    print("\n【日期超范围】")
    print(weather_out_of_range_sample())
